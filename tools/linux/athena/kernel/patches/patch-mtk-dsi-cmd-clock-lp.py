#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""mediatek-dsi: use an LP clock for LPM commands and the requested clock for video.

Backported from nuno407/techo5 commit 47717b743e2348d5e268d07b303ec04ded966111,
custom-kernel/athena/patches/mtk-dsi-cmd-clock-lp.py. Linux 6.18 already leaves high-speed
transmission off during initialization. Restore the video clock after lane_ready, which can
initialize DSI_TXRX_CTRL.

BOE-new is the only Athena panel requesting LPM commands with continuous video. Other JD9365
panels have no LPM flag; all Athena ILI9881C panels request a non-continuous clock already.
Their clock configuration stays the same. Usage: patch-mtk-dsi-cmd-clock-lp.py <linux tree>.
Idempotent.
"""
import os
import sys

RXTX_OLD = """\tif (dsi->mode_flags & MIPI_DSI_CLOCK_NON_CONTINUOUS)
\t\tregval |= HSTX_CKLP_EN;
"""
RXTX_NEW = """\t/* LPM commands need an LP clock; video restores the panel's requested clock. */
\tif (dsi->mode_flags & (MIPI_DSI_CLOCK_NON_CONTINUOUS | MIPI_DSI_MODE_LPM))
\t\tregval |= HSTX_CKLP_EN;
"""
ENABLE_OLD = """\tmtk_dsi_lane_ready(dsi);
\tmtk_dsi_set_mode(dsi);
\tmtk_dsi_clk_hs_mode(dsi, 1);
"""
ENABLE_NEW = """\tmtk_dsi_lane_ready(dsi);
\tif ((dsi->mode_flags & MIPI_DSI_MODE_LPM) &&
\t    !(dsi->mode_flags & MIPI_DSI_CLOCK_NON_CONTINUOUS))
\t\tmtk_dsi_mask(dsi, DSI_TXRX_CTRL, HSTX_CKLP_EN, 0);
\tmtk_dsi_set_mode(dsi);
\tmtk_dsi_clk_hs_mode(dsi, 1);
"""
PARTS = ((RXTX_OLD, RXTX_NEW), (ENABLE_OLD, ENABLE_NEW))


def main():
    path = os.path.join(sys.argv[1], "drivers/gpu/drm/mediatek/mtk_dsi.c")
    with open(path) as f:
        s = f.read()
    for old, new in PARTS:
        if new in s:
            continue
        assert s.count(old) == 1, "mtk-dsi-cmd-clock-lp: mtk_dsi.c is not the one expected (%r)" % old[:40]
        s = s.replace(old, new)
    with open(path, "w") as f:
        f.write(s)


if __name__ == "__main__":
    main()
