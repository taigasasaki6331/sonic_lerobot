#!/bin/sh
# Run on G1 as root only after securing the grippers. Binding can toggle UART lines.
set -eu
cd -- "$(dirname -- "$0")"
test "$(id -u)" = 0
test "$(uname -r)" = 5.15.148-tegra
test "$(uname -m)" = aarch64
sha256sum -c module.sha256
modinfo -F vermagic ./ch341.ko | grep -q '^5.15.148-tegra '
modinfo -F alias ./ch341.ko | grep -q 'v1A86p7522'
test ! -e /sys/module/ch341
test ! -e /lib/modules/5.15.148-tegra/updates/g1-pika/ch341.ko
test ! -e /etc/udev/rules.d/70-g1-pika-serial.rules
test ! -e /dev/pika/right/gripper
# Install rules first, so ModemManager will not probe newly created PIKA ports.
install -m 0644 70-g1-pika-serial.rules /etc/udev/rules.d/70-g1-pika-serial.rules
udevadm control --reload-rules
install -D -m 0644 ch341.ko /lib/modules/5.15.148-tegra/updates/g1-pika/ch341.ko
depmod -a 5.15.148-tegra
modprobe ch341
udevadm settle --timeout=10
ls -l /dev/pika/right/gripper /dev/serial/by-path
modinfo -F filename ch341
printf '%s\n' 'Driver loaded; serial ports were NOT opened. Verify both USB driver bindings.'
