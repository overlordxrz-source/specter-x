# The lab credential is NOT in Git.
#
# The build reads the WPA2 passphrase from the environment and generates a
# header INTO THE BUILD DIRECTORY, which is gitignored. The secret
# therefore never enters the source tree, never reaches Git, and never
# appears in a tracked file.
#
# Where the value comes from:
#
#   tools/lab_credentials.py init   writes firmware/esp32-csi/softap_csi/lab.env
#                                   (gitignored, mode 600) with a random
#                                   passphrase, and prints the path - not
#                                   the secret.
#   tools/lab_credentials.py env    prints the export line for the shell.
#
# The build FAILS CLOSED: with no credential it will not produce an open
# lab network, because an accidentally open lab AP is a real and silent
# failure. An open build has to be asked for explicitly.
set(SPECTER_LAB_PSK "$ENV{SPECTER_LAB_PSK}")

if(NOT SPECTER_LAB_PSK)
    if(SPECTER_LAB_ALLOW_OPEN)
        message(WARNING
            "SPECTER_LAB_ALLOW_OPEN was set: this image publishes an OPEN "
            "lab network. That is a deliberate choice, not a default.")
        set(SPECTER_LAB_PSK "")
    else()
        message(FATAL_ERROR
            "No lab credential found.\n"
            "  The lab network's WPA2 passphrase must NOT be committed. Put it "
            "in\n"
            "  firmware/esp32-csi/softap_csi/lab.env (gitignored) with\n"
            "      tools/lab_credentials.py init\n"
            "  or export SPECTER_LAB_PSK in the build environment. To build an "
            "open\n"
            "  lab image on purpose, pass -DSPECTER_LAB_ALLOW_OPEN=ON.")
    endif()
endif()

# The passphrase goes into a 64-byte field in wifi_config_t, and WPA2
# requires 8..63 characters. Restricting the alphabet also means the value
# cannot need escaping into a C string literal, which is a class of bug
# worth not having in a build step.
if(SPECTER_LAB_PSK)
    string(LENGTH "${SPECTER_LAB_PSK}" _psk_len)
    if(_psk_len LESS 8 OR _psk_len GREATER 63)
        message(FATAL_ERROR
            "The lab passphrase must be 8..63 characters (WPA2), got ${_psk_len}.")
    endif()
    if(NOT SPECTER_LAB_PSK MATCHES "^[A-Za-z0-9!@#%^&*()_+=,.:?~-]+$")
        message(FATAL_ERROR
            "The lab passphrase must use only letters, digits and the "
            "punctuation ! @ # % ^ & * ( ) _ + = , . : ? ~ - so that it "
            "needs no escaping.")
    endif()
endif()

# The header is written rather than configured from a template, because the
# IDF runs a "requirements" pass over this file before the real configure,
# and a template lookup in that pass fails. The file is written to the
# component's BINARY directory, which is inside the build tree and
# gitignored, so the secret never enters the source tree.
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/lab_credentials.h"
"/* GENERATED FILE - DO NOT EDIT.\n"
" *\n"
" * Produced by the build from the environment (or from the gitignored\n"
" * firmware/esp32-csi/softap_csi/lab.env that tools/lab_credentials.py\n"
" * writes). It lands in the BUILD DIRECTORY, which is gitignored, so the\n"
" * lab credential never enters the source tree and never reaches Git.\n"
" */\n"
"#pragma once\n"
"\n"
"#define SPECTER_LAB_PSK \"${SPECTER_LAB_PSK}\"\n")

idf_component_register(
    SRCS "app_main.c"
          "dq_ring.c"
          "csi_output.c"
    INCLUDE_DIRS "." "${CMAKE_CURRENT_BINARY_DIR}"
    REQUIRES esp_wifi esp_netif esp_event nvs_flash lwip spi_flash
)
