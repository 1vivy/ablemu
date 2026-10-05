import binascii
import os
import struct

import defines

# Default image directory for the historical (Samsung-oriented) layout. It is
# only consulted when no explicit partition set is supplied.
DEFAULT_IMAGES_DIR = "samsung-imgs/"

# Fixed identities for the synthesized GPT. The partition type is "Linux
# filesystem data"; Android's ABL resolves partitions by label, not type.
GPT_SIGNATURE = b"EFI PART"
GPT_REVISION = 0x00010000
GPT_HEADER_SIZE = 92
GPT_ENTRY_COUNT = 128
GPT_ENTRY_SIZE = 128
GPT_TYPE_LINUX_FS = bytes.fromhex("af3dc60f838472478e793d69d8477de4")
GPT_DISK_GUID = bytes.fromhex("6f1a0f5b7c3d4e2a9b8c7d6e5f4a3b2c")
GPT_ENTRY_LBA = 2


def _gpt_entry(name, starting_lba, ending_lba, unique_guid):
    encoded = name.encode("utf-16-le")
    if len(encoded) > 72:
        encoded = encoded[:72]
    payload = struct.pack(
        "<16s16sQQQ72s",
        GPT_TYPE_LINUX_FS,
        unique_guid,
        starting_lba,
        ending_lba,
        0,
        encoded,
    )
    return payload


def _unique_guid(name):
    seed = binascii.crc32(name.encode()) & 0xFFFFFFFF
    return struct.pack("<IHH8B", seed, 0x4A68, 0x9C8F, 0x1B, 0x1A, 0x23, 0xA1, 0x00, 0x01)


def build_gpt(partition_list, block_size):
    """Synthesize a protective-MBR + GPT disk image for the partition list.

    The ABL enumerates the whole disk through BlockIO and parses the GPT to
    resolve a partition label to a partition handle; without a readable GPT the
    lookup reports "efi no media". Start/size LBA values here match the
    DevicePath nodes built in protocols.py, so both lookups agree.
    """
    entries_lbas = (GPT_ENTRY_COUNT * GPT_ENTRY_SIZE + block_size - 1) // block_size
    total_lba = partition_list.total_lba
    image = bytearray(total_lba * block_size)

    mbr = bytearray(512)
    mbr[446] = 0x00
    mbr[447:450] = b"\x00\x02\x00"
    mbr[450] = 0xEE
    mbr[451:454] = b"\xff\xff\xff"
    struct.pack_into("<II", mbr, 454, 1, min(total_lba - 1, 0xFFFFFFFF))
    mbr[510:512] = b"\x55\xaa"
    image[0:512] = mbr

    entries_offset = GPT_ENTRY_LBA * block_size
    for index, partition in enumerate(partition_list.get_partition_list()):
        entry = _gpt_entry(
            partition["partition_name"],
            partition["starting_lba"],
            partition["ending_lba"],
            _unique_guid(partition["partition_name"]),
        )
        start = entries_offset + index * GPT_ENTRY_SIZE
        image[start : start + GPT_ENTRY_SIZE] = entry

    entries_crc = binascii.crc32(
        bytes(image[entries_offset : entries_offset + GPT_ENTRY_COUNT * GPT_ENTRY_SIZE])
    ) & 0xFFFFFFFF
    first_usable = GPT_ENTRY_LBA + entries_lbas
    last_usable = total_lba - entries_lbas - 2
    header = struct.pack(
        "<8sIIIIQQQQ16sQIII",
        GPT_SIGNATURE,
        GPT_REVISION,
        GPT_HEADER_SIZE,
        0,
        0,
        1,
        total_lba - 1,
        first_usable,
        last_usable,
        GPT_DISK_GUID,
        GPT_ENTRY_LBA,
        GPT_ENTRY_COUNT,
        GPT_ENTRY_SIZE,
        entries_crc,
    )
    header_crc = binascii.crc32(header) & 0xFFFFFFFF
    header = struct.pack(
        "<8sIIIIQQQQ16sQIII",
        GPT_SIGNATURE,
        GPT_REVISION,
        GPT_HEADER_SIZE,
        header_crc,
        0,
        1,
        total_lba - 1,
        first_usable,
        last_usable,
        GPT_DISK_GUID,
        GPT_ENTRY_LBA,
        GPT_ENTRY_COUNT,
        GPT_ENTRY_SIZE,
        entries_crc,
    )
    image[block_size : block_size + GPT_HEADER_SIZE] = header
    return bytes(image)


class PartitionList:
    def __init__(self):
        self.partition_list = []
        # Explicit partition set: a list of {"partition_name", "path"} dicts.
        # When None the built-in default layout below is used.
        self.entries = None

    def set_partitions(self, entries):
        """Replace the built-in layout with an explicit name -> path list."""
        self.entries = [
            {"partition_name": entry["partition_name"], "path": entry["path"]}
            for entry in entries
        ]

    def _default_partitions(self, d):
        return [
            #{"partition_name": "frp", "path": "frp.img"},
            #{"partition_name": "devinfo", "path": "devinfo.img"},
            {"partition_name": "boot_a", "path": d + "boot.img"},
            {"partition_name": "boot_b", "path": d + "boot.img"},
            #{"partition_name": "system_a", "path": d + "system.img"},
            {"partition_name": "abl_a", "path": d + "abl.elf"},
            {"partition_name": "abl_b", "path": d + "abl.elf"},
            {"partition_name": "dtbo_a", "path": d + "dtbo.img"},
            {"partition_name": "dtbo_b", "path": d + "dtbo.img"},
            {"partition_name": "vbmeta_a", "path": d + "vbmeta.img"},
            {"partition_name": "vbmeta_b", "path": d + "vbmeta.img"},
            {"partition_name": "vendor_boot_a", "path": d + "vendor_boot.img"},
            {"partition_name": "vendor_boot_b", "path": d + "vendor_boot.img"},
            {"partition_name": "vbmeta_system_a", "path": d + "vbmeta_system.img"},
            {"partition_name": "vbmeta_system_b", "path": d + "vbmeta_system.img"},
            # {"partition_name": "recovery_a", "path": d + "recovery.img"},
            # {"partition_name": "recovery_b", "path": d + "recovery.img"},
            {"partition_name": "init_boot_a", "path": d + "init_boot.img"},
            {"partition_name": "init_boot_b", "path": d + "init_boot.img"},
            {"partition_name": "xbl_a", "path": d + "xbl.img"},
            {"partition_name": "tz_a", "path": d + "tz.img"},
            {"partition_name": "hyp_a", "path": d + "hyp.img"},
            {"partition_name": "efisp_a", "path": "abl.pe"},
            {"partition_name": "efisp", "path": "abl.pe"},
        ]

    def setup(self, fix):
        d = DEFAULT_IMAGES_DIR
        if self.entries is not None:
            self.partition_list = [
                {"partition_name": entry["partition_name"], "path": entry["path"]}
                for entry in self.entries
            ]
        else:
            self.partition_list = self._default_partitions(d)
        if fix == defines.FIX_SAMSUNG:
            self.partition_list.append({"partition_name": "param", "path": d + "param.img"})
            self.partition_list.append({"partition_name": "debug", "path": d + "debug.img"})
            self.partition_list.append({"partition_name": "optics_a", "path": d + "optics.img"})
            self.partition_list.append({"partition_name": "optics_b", "path": d + "optics.img"})
            self.partition_list.append({"partition_name": "prism_a", "path": d + "prism.img"})
            self.partition_list.append({"partition_name": "prism_b", "path": d + "prism.img"})
            self.partition_list.append({"partition_name": "btd", "path": d + "btd.img"})

        current_lba = 0
        for partition in self.partition_list:
            partition["size"] = os.path.getsize(partition["path"])
            partition["starting_lba"] = current_lba
            partition["ending_lba"] = current_lba + partition["size"] // defines.BLOCK_SIZE - 1
            current_lba += partition["size"] // defines.BLOCK_SIZE

        self.total_lba = current_lba

    def get_partition_list(self):
        return self.partition_list

    def get_partition(self, partition_name):
        for partition in self.partition_list:
            if partition["partition_name"] == partition_name:
                return partition
        return None

    def __len__(self):
        return len(self.partition_list)

    def __getitem__(self, index):
        return self.partition_list[index]
