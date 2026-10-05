"""Capture exactly what the bootloader hands the kernel.

The Android bootloader's last act is to branch to the Linux kernel entry point
with x0 pointing at the final device tree (arm64 boot protocol).  That instant
is the only producer-independent observation point: the kernel image, the
assembled initrd, the command line and the DTB already sit in emulated memory
in the state the kernel will parse them, whichever bootloader (OEM ABL, GBL,
...) assembled them.

This module therefore only *captures* bytes.  Deciding whether the kernel would
accept the initrd is a separate, host-side question (see the lab's analysis
step, which reuses the gbl-bds-rs independent parsers).
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

from unicorn import Uc, UcError
from unicorn.arm64_const import UC_ARM64_REG_X0

_X0 = UC_ARM64_REG_X0

FDT_MAGIC = 0xD00DFEED
IMAGE_MAGIC = 0x644D5241  # "ARM\x64" at offset 0x38 of the arm64 Image header
IMAGE_MAGIC_OFFSET = 0x38
IMAGE_HEADER_SIZE = 0x40
IMAGE_SEARCH_WINDOW = 64 * 1024 * 1024


def _read(uc: Uc, address: int, size: int) -> bytes:
    return bytes(uc.mem_read(address, size))


def _find_image_header(uc: Uc, entry: int) -> tuple[int, int] | None:
    """Locate the arm64 Image header that the entry point belongs to."""
    start = max(0, entry - IMAGE_SEARCH_WINDOW) & ~0xFFF
    for base in range(entry & ~0xFFF, start, -0x1000):
        try:
            header = _read(uc, base, IMAGE_HEADER_SIZE)
        except UcError:
            continue
        if struct.unpack_from("<I", header, IMAGE_MAGIC_OFFSET)[0] != IMAGE_MAGIC:
            continue
        image_size = struct.unpack_from("<Q", header, 0x10)[0]
        if 0 < image_size <= IMAGE_SEARCH_WINDOW:
            return base, image_size
    return None


def _fdt_properties(raw: bytes) -> dict[str, bytes]:
    if len(raw) < 40 or struct.unpack_from(">I", raw, 0)[0] != FDT_MAGIC:
        raise ValueError("not a device tree")
    header = struct.unpack_from(">10I", raw, 0)
    struct_off, strings_off = header[2], header[3]
    strings_size, struct_size = header[8], header[9]
    structure = raw[struct_off : struct_off + struct_size]
    strings = raw[strings_off : strings_off + strings_size]
    offset = 0
    stack: list[str] = []
    properties: dict[str, bytes] = {}
    while offset + 4 <= len(structure):
        token = struct.unpack_from(">I", structure, offset)[0]
        offset += 4
        if token == 1:  # FDT_BEGIN_NODE
            end = structure.find(b"\0", offset)
            if end < 0:
                break
            stack.append(structure[offset:end].decode("ascii", "replace"))
            offset = (end + 4) & ~3
        elif token == 2:  # FDT_END_NODE
            if stack:
                stack.pop()
        elif token == 3:  # FDT_PROP
            length, name_offset = struct.unpack_from(">II", structure, offset)
            offset += 8
            name_end = strings.find(b"\0", name_offset)
            name = strings[name_offset:name_end].decode("ascii", "replace")
            node = "/" + "/".join(part for part in stack if part)
            properties[f"{node}/{name}"] = structure[offset : offset + length]
            offset = (offset + length + 3) & ~3
        elif token == 4:  # FDT_NOP
            continue
        else:  # FDT_END
            break
    return properties


def _u64(value: bytes) -> int:
    return int.from_bytes(value, "big")


def _read_fdt(uc: Uc, address: int) -> bytes:
    try:
        header = _read(uc, address, 40)
    except UcError:
        return b""
    if struct.unpack_from(">I", header, 0)[0] != FDT_MAGIC:
        return b""
    total = struct.unpack_from(">I", header, 4)[0]
    if total < 40 or total > 0x4000000:
        return b""
    try:
        return _read(uc, address, total)
    except UcError:
        return b""


def capture(uc: Uc, entry: int, output: Path) -> dict[str, object]:
    """Write the kernel handoff artifacts; return a summary record."""
    output.mkdir(parents=True, exist_ok=True)
    dtb_address = uc.reg_read(UC_ARM64_REG_X0)
    summary: dict[str, object] = {
        "entry": entry,
        "registers": {f"x{index}": uc.reg_read(_X0 + index) for index in range(4)},
        "dtb_address": dtb_address,
    }
    raw_fdt = _read_fdt(uc, dtb_address)
    if raw_fdt:
        (output / "fdt.bin").write_bytes(raw_fdt)
        summary["fdt_size"] = len(raw_fdt)
        try:
            props = _fdt_properties(raw_fdt)
        except ValueError:
            props = {}
        bootargs = props.get("/chosen/bootargs", b"").split(b"\0", 1)[0]
        (output / "cmdline.txt").write_bytes(bootargs + b"\n")
        summary["cmdline"] = bootargs.decode("utf-8", "replace")
        for name in ("linux,initrd-start", "linux,initrd-end"):
            value = props.get(f"/chosen/{name}")
            if value:
                summary[name] = _u64(value)
        start = summary.get("linux,initrd-start")
        end = summary.get("linux,initrd-end")
        if isinstance(start, int) and isinstance(end, int) and end > start:
            ramdisk = _read(uc, start, end - start)
            (output / "ramdisk.bin").write_bytes(ramdisk)
            summary["ramdisk_size"] = len(ramdisk)
    image = _find_image_header(uc, entry)
    if image is not None:
        base, image_size = image
        (output / "kernel.bin").write_bytes(_read(uc, base, image_size))
        summary["kernel_address"] = base
        summary["kernel_size"] = image_size
    (output / "handoff.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary
