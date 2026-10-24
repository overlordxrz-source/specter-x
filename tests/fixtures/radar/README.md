# Radar reference fixture

`iwr6843aop_oob_points_2.bin` is a deterministic, spec-conformant TI mmWave
out-of-box-demo UART packet. It is **not** a hardware capture and is not
evidence of radar performance. It exists to freeze the byte layout used by the
offline parser tests.

## Source contract

TI documents the UART output packet as:

- a 40-byte `MmwDemo_output_message_header_t`;
- a count of TLV items, each with an 8-byte `MmwDemo_output_message_tl_t`
  header (`type:uint32`, `payload length:uint32`) followed by its payload;
- a total packet length that includes the header and is padded to a multiple
  of 32 bytes.

The detected-points TLV (type `1`) payload is
`numDetectedObj x DPIF_PointCloudCartesian_t`: four little-endian `float32`
values per point (`x`, `y`, `z`, radial velocity). The 40-byte header fields
used here are the documented order:

```text
magic(8) version u32 totalPacketLen u32 platform u32 frameNumber u32
timeCpuCycles u32 numDetectedObj u32 numTLVs u32 subFrameNumber u32
```

References:

- TI, *Understanding UART Data Output Format*:
  <https://dev.ti.com/tirex/explore/node?node=A__ADnbI7zK9bSRgZqeAxprvQ__radar_toolbox__1AslXXD__LATEST>
- TI, *Millimeter Wave (mmw) Demo for XWR16XX*, “Output information sent to
  host”:
  <https://prod-dcd-datasets-public-files-eu-west-1.s3.eu-west-1.amazonaws.com/5c4dbaf2-9391-4d39-b995-2fcc9ae45115>

The exact board/SDK version was not available in this offline task. The
fixture therefore records `version = 0x03060000` and `platform = 0x6843` as
fixture metadata; the parser deliberately does not enforce a particular
version or platform.

## Frozen bytes

- Size: 96 bytes
- Header: `version=0x03060000`, `totalPacketLen=96`, `platform=0x6843`,
  `frameNumber=7`, `timeCpuCycles=0`, `numDetectedObj=2`, `numTLVs=1`,
  `subFrameNumber=0`
- TLV: type `1`, payload length `32`
- Points: `[1.0, 2.0, 0.5, -0.1]`, `[0.2, 3.0, 0.0, 0.4]`
- Trailing zero padding: 16 bytes
- SHA-256:
  `ea26d5ef056ced916ee39f3b6120cffa8c6acb335fdff94326cad80b4dd1d8db`
