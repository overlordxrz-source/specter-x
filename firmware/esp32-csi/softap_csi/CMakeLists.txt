# The SPECTER-X controlled-link firmware.
#
# It keeps Espressif's `csi_recv_router` wire format EXACTLY, so the host
# parser is unchanged, and it fixes the two things that were wrong with the
# original image:
#
#   1. the CSI callback no longer formats or prints - it copies the raw
#      bytes into a queue and returns, because the IDF documents that the
#      callback runs in the Wi-Fi task and must not do lengthy work;
#   2. a single writer task does all the output, so lines can never
#      interleave and the host never sees a torn record.
#
# See README.md for the roles and the capability probe.
cmake_minimum_required(VERSION 3.16)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(specter_csi_lab)
