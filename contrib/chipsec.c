/* Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
 * SPDX-License-Identifier: GPL-2.0+ */

#include <efi.h>
#include <efilib.h>

EFI_STATUS EFIAPI
efi_main (EFI_HANDLE ImageHandle, EFI_SYSTEM_TABLE *SystemTable)
{
	InitializeLib(ImageHandle, SystemTable);
	Print(L"DO NOT TRUST\n");
	return EFI_SUCCESS;
}
