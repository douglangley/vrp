"""Diff two KG-UV96M images and show what changed in the SETTINGS struct.

The channel/name/valid tables (and their +0x4000 firmware mirror) are ignored,
so only radio-wide settings bytes are reported. Feed it a baseline and an
"after" image from read_image.py; the changed bytes at 0x0420-0x04bf are the
setting(s) you touched. See docs/kg-uv96m-settings/PLAN.md.

    uv run python tools/kg-uv96m/diff_images.py baseline.img after.img
"""
import sys

# Regions that are channel data (not settings), plus their +0x4000 mirror.
_CHAN_LIKE = [(0x05e0, 0x1ee0), (0x1f00, 0x31c0), (0x3200, 0x3391)]


def _is_channel_byte(a):
    for lo, hi in _CHAN_LIKE:
        if lo <= a < hi or lo + 0x4000 <= a < hi + 0x4000:
            return True
    return False


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return
    base = open(sys.argv[1], "rb").read()
    aft = open(sys.argv[2], "rb").read()

    diffs = [i for i in range(min(len(base), len(aft)))
             if base[i] != aft[i] and not _is_channel_byte(i)]
    # collapse to contiguous runs
    groups = []
    for a in diffs:
        if groups and a == groups[-1][-1] + 1:
            groups[-1].append(a)
        else:
            groups.append([a])

    print("settings-region changes: %d bytes in %d group(s)\n" % (
        len(diffs), len(groups)))
    for g in groups:
        # skip the +0x4000 mirror in the printout (identical to primary)
        if g[0] >= 0x4000:
            continue
        b = " ".join("%02x" % base[x] for x in g)
        a = " ".join("%02x" % aft[x] for x in g)
        ab = "".join(chr(base[x]) if 32 <= base[x] < 127 else "." for x in g)
        aa = "".join(chr(aft[x]) if 32 <= aft[x] < 127 else "." for x in g)
        print("  0x%04x  %s |%s|  ->  %s |%s|" % (g[0], b, ab, a, aa))
    print("\n(+0x4000 mirror copies omitted; the radio maintains those itself.)")


if __name__ == "__main__":
    main()
