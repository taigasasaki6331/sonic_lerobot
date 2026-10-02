// Read-only V4L2 format, timing and controls. Never sets controls or streams.
#include <fcntl.h>
#include <linux/videodev2.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>
int main(int argc, char **argv) {
  if (argc != 2) return 2;
  int fd = open(argv[1], O_RDONLY | O_NONBLOCK);
  if (fd < 0) { perror("open"); return 1; }
  struct v4l2_format fmt = {.type = V4L2_BUF_TYPE_VIDEO_CAPTURE};
  if (ioctl(fd, VIDIOC_G_FMT, &fmt) == 0)
    printf("format=%c%c%c%c width=%u height=%u\n", fmt.fmt.pix.pixelformat & 255,
      (fmt.fmt.pix.pixelformat >> 8) & 255, (fmt.fmt.pix.pixelformat >> 16) & 255,
      (fmt.fmt.pix.pixelformat >> 24) & 255, fmt.fmt.pix.width, fmt.fmt.pix.height);
  struct v4l2_streamparm parm = {.type = V4L2_BUF_TYPE_VIDEO_CAPTURE};
  if (ioctl(fd, VIDIOC_G_PARM, &parm) == 0)
    printf("interval=%u/%u seconds\n", parm.parm.capture.timeperframe.numerator,
      parm.parm.capture.timeperframe.denominator);
  struct v4l2_queryctrl q = {.id = V4L2_CTRL_FLAG_NEXT_CTRL};
  while (ioctl(fd, VIDIOC_QUERYCTRL, &q) == 0) {
    struct v4l2_control c = {.id = q.id};
    if (!(q.flags & V4L2_CTRL_FLAG_DISABLED) && ioctl(fd, VIDIOC_G_CTRL, &c) == 0)
      printf("control=0x%x name=%s current=%d min=%d max=%d default=%d\n",
        q.id, q.name, c.value, q.minimum, q.maximum, q.default_value);
    q.id |= V4L2_CTRL_FLAG_NEXT_CTRL;
  }
  close(fd);
  return 0;
}
