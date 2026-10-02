"""Build matched MuJoCo/Pinocchio models with two closed, fixed PIKA grippers.

The committed legacy generator supplies attachment transforms and inertias.
Original hand geometry/dynamics are removed; the 29 G1 actuators stay unchanged.
Generated files live under artifacts/models, never in either source repository.
"""

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation


def numbers(values):
    return " ".join(f"{x:.16g}" for x in values)


def quaternion(rpy):
    return np.roll(Rotation.from_euler("xyz", np.fromstring(rpy, sep=" ")).as_quat(), 1)


def urdf_inertial_to_mj(inertial):
    origin = inertial.find("origin")
    inertia = inertial.find("inertia")
    matrix = np.array([[float(inertia.get("i" + a + b if a <= b else "i" + b + a))
                        for b in "xyz"] for a in "xyz"])
    rotation = Rotation.from_euler("xyz", np.fromstring(origin.get("rpy", "0 0 0"), sep=" ")).as_matrix()
    matrix = rotation @ matrix @ rotation.T
    eigen = np.linalg.eigvalsh(matrix)
    if min(eigen) <= 0 or eigen[-1] > sum(eigen[:-1]):
        raise ValueError("Invalid legacy PIKA inertia")
    return ET.Element("inertial", {
        "pos": origin.get("xyz", "0 0 0"), "mass": inertial.find("mass").get("value"),
        "fullinertia": numbers([matrix[0, 0], matrix[1, 1], matrix[2, 2], matrix[0, 1], matrix[0, 2], matrix[1, 2]]),
    })


def build_pika_model(upstream, root):
    assets = root / "assets/pika"
    provenance = json.loads((assets / "provenance.json").read_text())
    for name, expected in provenance["files_sha256"].items():
        if hashlib.sha256((assets / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"Migrated PIKA asset checksum mismatch: {name}")
    output = root / "artifacts/models"
    output.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("legacy_pika_generator", assets / "source/generate_urdf.py")
    legacy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy)
    resources = upstream / "decoupled_wbc/sim2mujoco/resources/robots/g1"
    robot_assets = upstream / "decoupled_wbc/control/robot_model/model_data/g1"
    urdf = ET.parse(robot_assets / "g1_29dof_with_hand.urdf")
    robot = urdf.getroot()
    robot.set("name", "g1_pika_closed")
    for element in list(robot):
        if element.get("name", "").startswith(("left_hand_", "right_hand_")):
            robot.remove(element)
    for mesh in robot.findall(".//mesh"):
        mesh.set("filename", str(robot_assets / mesh.get("filename")))

    scene = ET.parse(resources / "g1_gear_wbc.xml")
    mj = scene.getroot()
    mj.set("model", "g1_pika_closed")
    mj.find("compiler").set("meshdir", str(resources / "meshes"))
    for body in mj.findall(".//body"):
        for child in list(body):
            if child.get("name", "").startswith(("left_hand_", "right_hand_")) or child.get("mesh", "").startswith(("left_hand_", "right_hand_")):
                body.remove(child)
    for side in ("left", "right"):
        wrist_name = f"{side}_wrist_yaw_link"
        wrist = mj.find(f".//body[@name='{wrist_name}']")
        # The MJ wrist inertia includes the original palm. The upstream URDF
        # separates the bare wrist (84.57647 g), which is retained here.
        wrist.remove(wrist.find("inertial"))
        wrist.insert(0, urdf_inertial_to_mj(robot.find(f"link[@name='{wrist_name}']/inertial")))
        legacy.add_pika(robot, side)

    # Synchronize G1 inertias with the dynamics model used by the balance policy.
    # This also removes pre-existing URDF/MJ dynamics differences from gravity compensation.
    body_names = {body.get("name") for body in mj.findall(".//body")}
    parents = {child: parent for parent in mj.iter() for child in parent}
    for body in mj.findall(".//body"):
        for joint in body.findall("joint"):
            if joint.get("type") == "free":
                continue
            uj = robot.find(f"joint[@name='{joint.get('name')}']")
            if (uj is None or uj.find("child").get("link") != body.get("name")
                    or uj.find("parent").get("link") != parents[body].get("name")
                    or joint.get("pos", "0 0 0") != "0 0 0"):
                raise RuntimeError("Unexpected G1 joint topology")
            # Upstream URDF and MJCF differ in waist/shoulder offsets; use MJCF
            # as the common G1 source so FK agrees away from the zero posture.
            rotation = Rotation.from_quat(np.roll(np.fromstring(body.get("quat", "1 0 0 0"), sep=" "), -1))
            uj.find("origin").set("xyz", body.get("pos", "0 0 0"))
            uj.find("origin").set("rpy", numbers(rotation.as_euler("xyz")))
            uj.find("axis").set("xyz", joint.get("axis", "0 0 1"))
    for link in robot.findall("link"):
        # Fixed head/logo/contour/support inertia is already merged into MJ
        # parent bodies. Preserve their frames/visuals, not duplicate inertia.
        if link.get("name") not in body_names and "_pika_" not in link.get("name"):
            if link.find("inertial") is not None:
                link.remove(link.find("inertial"))
    for body in mj.findall(".//body"):
        inertial = body.find("inertial")
        link = robot.find(f"link[@name='{body.get('name')}']")
        if inertial is None or link is None:
            continue
        if link.find("inertial") is not None:
            link.remove(link.find("inertial"))
        new = ET.SubElement(link, "inertial")
        ET.SubElement(new, "origin", {"xyz": inertial.get("pos", "0 0 0"), "rpy": "0 0 0"})
        ET.SubElement(new, "mass", {"value": inertial.get("mass")})
        if "fullinertia" in inertial.attrib:
            a, b, c, d, e, f = np.fromstring(inertial.get("fullinertia"), sep=" ")
            matrix = np.array([[a, d, e], [d, b, f], [e, f, c]])
        else:
            rotation = Rotation.from_quat(np.roll(np.fromstring(inertial.get("quat", "1 0 0 0"), sep=" "), -1)).as_matrix()
            matrix = rotation @ np.diag(np.fromstring(inertial.get("diaginertia"), sep=" ")) @ rotation.T
        ET.SubElement(new, "inertia", {"i" + "xyz"[a] + "xyz"[b]: str(matrix[a, b])
                                      for a, b in [(0, 0), (1, 1), (2, 2), (0, 1), (0, 2), (1, 2)]})

    for mesh in robot.findall(".//mesh"):
        if mesh.get("filename").startswith("package://g1_pika_description/"):
            mesh.set("filename", str(assets / Path(mesh.get("filename")).name))
    for filename in ("gripper_base.STL", "link7.STL", "link8.STL"):
        ET.SubElement(mj.find("asset"), "mesh", {"name": "pika_" + Path(filename).stem, "file": str(assets / filename)})

    for joint in robot.findall("joint"):
        child_name = joint.find("child").get("link")
        if "_pika_" not in child_name:
            continue
        # Static fingers preserve the legacy q=0 mass distribution. No hidden
        # extra DOFs are introduced into the policy's 29-joint observation.
        joint.set("type", "fixed")
        for tag in ("axis", "limit"):
            if joint.find(tag) is not None:
                joint.remove(joint.find(tag))
        origin = joint.find("origin")
        parent = mj.find(f".//body[@name='{joint.find('parent').get('link')}']")
        body = ET.SubElement(parent, "body", {"name": child_name,
            "pos": origin.get("xyz", "0 0 0"), "quat": numbers(quaternion(origin.get("rpy", "0 0 0")))})
        link = robot.find(f"link[@name='{child_name}']")
        if link.find("inertial") is not None:
            body.append(urdf_inertial_to_mj(link.find("inertial")))
        visual = link.find("visual")
        if visual is not None:
            filename = Path(visual.find("geometry/mesh").get("filename"))
            geom = {"name": child_name + "_collision", "type": "mesh", "mesh": "pika_" + filename.stem,
                    "rgba": "0.3 0.55 0.8 1", "contype": "1", "conaffinity": "1", "density": "0"}
            ET.SubElement(body, "geom", geom)
            # URDF geometry is for inspection; dynamics use explicit inertias.
            collision = deepcopy(visual)
            collision.tag = "collision"
            if collision.find("material") is not None:
                collision.remove(collision.find("material"))
            link.append(collision)
        if child_name.endswith("_pika_tcp"):
            ET.SubElement(body, "site", {"name": child_name + "_site", "size": "0.007", "rgba": "1 0.2 0.1 1"})

    urdf_path, xml_path = output / "g1_pika_closed.urdf", output / "g1_pika_closed.xml"
    for tree, path in ((urdf, urdf_path), (scene, xml_path)):
        ET.indent(tree, space="  ")
        tree.write(path, encoding="utf-8", xml_declaration=True)
    mass = sum(float(link.find("inertial/mass").get("value")) for link in robot.findall("link")
               if "_pika_" in link.get("name") and link.find("inertial/mass") is not None)
    report = {"pika_mass_each_kg": mass / 2, "pika_mass_total_kg": mass,
              "gripper_state": "fixed_at_legacy_q_zero", "mass_provenance": "legacy_URDF_not_measured",
              "mount_hardware_and_cables": "not_modelled", "collision": "convex_hull_per_mesh",
              "bare_wrist_mass_each_kg": 0.08457647}
    (output / "pika-model.json").write_text(json.dumps(report, indent=2) + "\n")
    return xml_path, urdf_path, report


def instantiate_pika_robot(urdf_path, upstream):
    from decoupled_wbc.control.robot_model.robot_model import RobotModel
    from decoupled_wbc.control.robot_model.supplemental_info.g1.g1_supplemental_info import G1SupplementalInfo

    info = G1SupplementalInfo()
    info.left_hand_actuated_joints = []
    info.right_hand_actuated_joints = []
    info.joint_groups["left_hand"] = {"joints": [], "groups": []}
    info.joint_groups["right_hand"] = {"joints": [], "groups": []}
    info.hand_frame_names = {side: f"{side}_pika_tcp" for side in ("left", "right")}
    return RobotModel(str(urdf_path), str(urdf_path.parent), supplemental_info=info)
