import defines
import os

class PartitionList:
    def __init__(self):
        self.partition_list = []

    def setup(self, fix):
        d = "samsung-imgs/"
        self.partition_list = [
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
            #try:
            partition["size"] = os.path.getsize(partition["path"])
            #except FileNotFoundError:
                
                #partition["size"] = 0x10000 * defines.BLOCK_SIZE
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
