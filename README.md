# ablemu

`ablemu` is a Qualcomm ABL (Android Bootloader) ARM64 emulator based on the [Unicorn Engine](https://www.unicorn-engine.org/). It provides a minimal UEFI environment to execute, trace, and debug ABL PE files (typically `LinuxLoader.efi` or `abl.elf`). It is suitable for security reasearch.

## Features

- **Fastboot commands**: Supports feeding fastboot commands.
- **UEFI Environment**: 
    - Minimal `EFI_SYSTEM_TABLE` and `EFI_BOOT_SERVICES` stubs.
    - Simplified stack and heap management.
- **Protocol Mocking**: Implements various UEFI protocols required by ABL, including:
    - `BlockIO`, `DevicePath`, `PartitionEntry`
    - `VerifiedBoot`, `KernelInterface`
    - `ChipInfo`, `PlatformInfo`, `ResetReason`
    - `QSEECom`, `QcomScm`, and more.
- **Boot Support**: Capable of "loading" a Linux kernel and DTB (stubs the loading process).
- **Integrated Debugger**: An interactive console for step execution, register inspection, and stack scanning.
- **Tracing**: Optional per-instruction tracing for deep analysis.

## Requirements

- Python 3.12+
- `unicorn`
- `pefile`

## Installation

```bash
# Install dependencies
pip install -r requirements.txt
```

## Usage

Place your `abl.elf` (or `abl.img`, `LinuxLoader.efi`) in the project root or provide the path. Optionally place other partitions like "boot", "vbmeta" or "devinfo" to emulate boot sequence and AVB verification. See `partitions.py` for partition information.

```bash
# Run the emulator
$ python emu.py abl.elf
[*] Trace mode: OFF  (set EMU_TRACE=1 to enable)
[PE] ImageBase        = 0x0000000000000000
[PE] SizeOfImage      = 0xA2000
[PE] AddressOfEntryPt = 0x1000
[PE] Number of sections: 3
  [.text   ]  VA=0x0000000000001000  VSize=0x80000  RawSize=0x80000
  [.data   ]  VA=0x0000000000081000  VSize=0x20000  RawSize=0x20000
  [.reloc  ]  VA=0x00000000000A1000  VSize=0x1000  RawSize=0x1000
[PE] Entry point (abs) = 0x0000000000001000
[INIT] GraphicsOutputProtocol at 0xDE020110, Mode at 0xDE020210, Info at 0xDE020310
[INIT] SimpleTextInputProtocol at 0xDE020450
[INIT] SimpleTextOutputProtocol at 0xDE0204B0, Mode at 0xDE020530
...
```

```
$ python emu.py abl.elf | grep ReportStatusCode
[ReportStatusCode] Loader Build Info: Jan 11 2026 06:25:40
[ReportStatusCode] Device Magic does not match
[ReportStatusCode] GetActiveSlot: First boot: set default slot _a
[ReportStatusCode] Total DDR Size: 0xe000000
[ReportStatusCode] KeyPress:0, BootReason:0
[ReportStatusCode] Fastboot=0, Recovery:0
[ReportStatusCode] SilentBoot Mode:11
[ReportStatusCode] GetVmData: ScmSipSysCall returned NULL
[ReportStatusCode] VM Hyp calls not present
```

```
$ python emu.py abl.elf --feed-cmd "getvar:all" --reset-reason 2 | grep -ai usb
       -> Found requests for EFI_USB_DEVICE_PROTOCOL, returning specific mock interface.
[UEFI] UsbDevice::AllocateTransferBuffer | Args: 0x2300000, 0x7EFFF8E8, 0x7EFFF758, 0x0, 0x7EFFF9AC, 0x4
       -> [GetVariable] VariableName: 'UsbfnMaxSpeed' GUID: QCOM
[UEFI] UsbDevice::StartEx | Args: 0x98958, 0x806E8, 0x0, 0x7EFFFA88, 0x7EFFFA94, 0xDE013000
       -> [UsbDevice::StartEx] Starting USB device with descriptor set at 0x98958
...
[UEFI] UsbDevice::Send | Args: 0x81, 0x15, 0xA3300000, 0x0, 0x1, 0x0
       -> [UsbDevice::Send] Send 21 bytes on endpoint 129 from 0xA3300000
       -> [UsbDevice::Send] Data: INFOhw-revision:10000
[UEFI] UsbDevice::HandleEvent | Args: 0x7EFFF82C, 0x7EFFF820, 0x7EFFF830, 0x0, 0x1, 0x0
       -> [UsbDevice::HandleEvent] Returning event type 2
[UEFI] UsbDevice::Send | Args: 0x81, 0x12, 0xA3300000, 0x0, 0x1, 0x0
       -> [UsbDevice::Send] Send 18 bytes on endpoint 129 from 0xA3300000
       -> [UsbDevice::Send] Data: INFOfactory-mode:1
...
```

Verified with the OnePlus 15 (infiniti, sm8850) LinuxLoader.efi and the device's own partition captures.

Also run against OnePlus 15 (infiniti, sm8850) `LinuxLoader.efi` with the device's
own `boot_b`/`vendor_boot_b`/`init_boot_b`/`recovery_b` captures: the ABL resolves
the partitions from the synthesized GPT, reads and hashes the AVB-signed images,
and then stops before the kernel branch because its slot decision needs platform
state this emulator does not provide yet.

That decision is LinuxLoader.efi's `0x1FC10` helper: it scans the ABL's in-RAM
partition table (entry count at `0xB80A70`, 0x84-byte entries starting at
`0x920B80`) for an entry whose name is the queried label followed by `_a` or
`_b`, and the byte it returns becomes the multi-slot flag in the loader context
(read at `0x23B44`). With the table empty the answer is "not multi-slot" and the
ABL enters fastboot instead of branching to the kernel, so a capture run only
reaches `--dump-dir` once that table is populated the way the platform firmware
populates it.

### Environment Variables

- `EMU_TRACE=1`: Enable per-instruction tracing.
- `EMU_DEBUG=1`: Start in interactive debug mode.
- `EMU_LOG_OFF=1`: Disable verbose logging for certain UEFI services.
- `EMU_PROTO_TRACE=1`: Log every BlockIo/DevicePath/PartitionEntry protocol request.

### Running against real device captures

The partition set is configurable, so a dump of a real device can be emulated
directly. Each `--partition NAME=PATH` exposes `NAME` as a block device backed
by `PATH`; the whole disk gets a synthesized GPT built from those names, sizes
and LBAs, which is what the ABL parses to resolve a label to a handle.

```bash
python emu.py LinuxLoader.efi \
    --partition boot_b=/captures/boot_b.img \
    --partition vendor_boot_b=/captures/vendor_boot_b.img \
    --partition init_boot_b=/captures/init_boot_b.img \
    --reset-reason 1
```

`--partitions-json FILE` takes the same list as JSON. When no partition set is
given a built-in demo layout is used.

The QCOM ABL partition-entry interface reports the **slot-less** label (`boot`,
not `boot_b`): the ABL appends `_a`/`_b` from the selected slot itself and
compares against that field, so a suffixed label makes every lookup miss.

### Dumping the kernel handoff

`--dump-dir DIR` captures what the bootloader hands the kernel at the moment it
branches to the kernel entry point: `kernel.bin` (located from the arm64 Image
header), `ramdisk.bin` (the assembled initrd, taken from
`/chosen/linux,initrd-start`/`-end`), `fdt.bin`, `cmdline.txt`, and
`handoff.json` with the entry point, registers and addresses. Whether the kernel
would *accept* that initrd is a separate host-side question; the module only
records the bytes.

### Interactive Debugger Commands

When in debug mode (or when a breakpoint is hit), you can use the following commands:

- `s`: Step into the next instruction.
- `c`: Continue execution.
- `r`: Dump general-purpose registers.
- `t`: Heuristic stack trace (scans the stack for return addresses).
- `u <addr> <size>`: Un-pause/Continue from a specific address.
- `q`: Quit the emulator.

## Project Structure

- `emu.py`: Main emulator entry point and UEFI logic.
- `defines.py`: Constants, GUIDs, and memory map definitions.
- `utils.py`: Utility functions for memory allocation, string reading, and hooking.
- `partitions.py`: Partition list and LBA mapping for storage emulation.
- `protocols.py`: Implementations of various UEFI protocols.
- `format_string.py`: Minimal `printf` style formatter for UEFI logs.

## License

MIT

## Acknowledgments

- [Unicorn Engine](https://www.unicorn-engine.org/)
- [codelinaro opensource abl](https://git.codelinaro.org/clo/la/abl/tianocore/edk2)
