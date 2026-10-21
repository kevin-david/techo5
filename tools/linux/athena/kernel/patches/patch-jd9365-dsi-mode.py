#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Set BOE-new timing and low-power initialization on Linux 6.18; leave other panels unchanged.

Backported from nuno407/techo5 commit 47717b743e2348d5e268d07b303ec04ded966111,
custom-kernel/athena/patches/jd9365-dsi-mode.py. The contributor measured LK's link at 478 Mbps
per lane. His 79.68 MHz, 108/22/32-pixel front/sync/back porches corrected moving flicker.

Linux 6.18 needs an optional descriptor mode_flags field and a probe fallback. Only BOE-new
overrides the old VIDEO | VIDEO_BURST | NO_EOT_PACKET default. Its flags add LPM and enable EOT
packets, as in the contributor's configuration. mediatek-dsi includes two bytes of EOT overhead
in its porch calculation. Keep that complete configuration: an earlier 6.18 build had stable text
and working touch on a second BOE-new unit. EOT behavior was not tested separately.

Usage: patch-jd9365-dsi-mode.py <linux tree>. Idempotent; apply after patch-display.py.
"""
import os
import re
import sys

FLAGS = "\t.mode_flags = MIPI_DSI_MODE_VIDEO | MIPI_DSI_MODE_VIDEO_BURST | MIPI_DSI_MODE_LPM,\n"
DESCS = ("athena_jd_boe_new_desc",)
# The boot loader's line: pixel clock (kHz), front porch, sync, back porch.
LK_LINE = {"athena_jd_boe_new_desc": (79680, 108, 22, 32)}
CLOCK_RE = r"(\t\t\.clock\t\t= )\d+,\t/\*[^*]*\*/"
H_RE = (r"(\t\t\.hsync_start\t= 800 \+ )\d+(,\n\t\t\.hsync_end\t= 800 \+ )\d+ \+ \d+"
        r"(,\n\t\t\.htotal\t\t= 800 \+ )\d+ \+ \d+ \+ \d+,")
DESC_OLD = "\tenum mipi_dsi_pixel_format format;\n\tint (*init)(struct jadard *jadard);"
DESC_NEW = "\tenum mipi_dsi_pixel_format format;\n\tunsigned long mode_flags;\n\tint (*init)(struct jadard *jadard);"
PROBE_OLD = """\tdsi->mode_flags = MIPI_DSI_MODE_VIDEO | MIPI_DSI_MODE_VIDEO_BURST |
\t\t\t  MIPI_DSI_MODE_NO_EOT_PACKET;"""
PROBE_NEW = """\tdsi->mode_flags = desc->mode_flags ? desc->mode_flags :
\t\tMIPI_DSI_MODE_VIDEO | MIPI_DSI_MODE_VIDEO_BURST | MIPI_DSI_MODE_NO_EOT_PACKET;"""


def desc(s, name):
    m = re.search(r"static const struct jadard_panel_desc %s = \{\n(.*?)\n\};\n" % name, s, re.S)
    assert m, "jd9365-dsi-mode: %s not found (panel/0004 not applied?)" % name
    return m


def main():
    path = os.path.join(sys.argv[1], "drivers/gpu/drm/panel/panel-jadard-jd9365da-h3.c")
    with open(path) as f:
        s = f.read()
    for old, new in ((DESC_OLD, DESC_NEW), (PROBE_OLD, PROBE_NEW)):
        if new not in s:
            assert s.count(old) == 1, "jd9365-dsi-mode: unexpected 6.18 descriptor or probe"
            s = s.replace(old, new)
    for name in DESCS:
        m = desc(s, name)
        body = m.group(1)
        if name in LK_LINE:
            clock, hfp, hsa, hbp = LK_LINE[name]
            body, n = re.subn(CLOCK_RE, lambda c: c.group(1) + "%d,\t/* the boot loader's line: 478 Mbps a lane */" % clock, body)
            assert n == 1, "jd9365-dsi-mode: %s clock" % name
            body, n = re.subn(H_RE, lambda h: "%s%d%s%d + %d%s%d + %d + %d," % (
                h.group(1), hfp, h.group(2), hfp, hsa, h.group(3), hfp, hsa, hbp), body)
            assert n == 1, "jd9365-dsi-mode: %s horizontal timing" % name
        if FLAGS.rstrip("\n") not in body:
            assert ".mode_flags" not in body, "jd9365-dsi-mode: %s already sets mode_flags" % name
            fmt = "\t.format = MIPI_DSI_FMT_RGB888,"
            assert body.count(fmt) == 1, "jd9365-dsi-mode: %s format line" % name
            body = body.replace(fmt, fmt + "\n" + FLAGS.rstrip("\n"))
        s = s[:m.start(1)] + body + s[m.end(1):]
    with open(path, "w") as f:
        f.write(s)


if __name__ == "__main__":
    main()
