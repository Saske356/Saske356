CC      := gcc
AS      := nasm
LD      := ld
CFLAGS  := -m32 -ffreestanding -fno-pie -fno-stack-protector -nostdlib -fno-builtin \
           -O2 -Wall -Wextra -std=gnu11 -Ikernel
LDFLAGS := -m elf_i386 -z noexecstack -T linker.ld -nostdlib

C_SRC   := $(wildcard kernel/*.c)
OBJ     := build/boot.o $(patsubst kernel/%.c,build/%.o,$(C_SRC))
KERNEL  := build/saskeos.bin

all: $(KERNEL)

build:
	mkdir -p build

build/boot.o: boot/boot.asm | build
	$(AS) -f elf32 $< -o $@

build/%.o: kernel/%.c kernel/*.h | build
	$(CC) $(CFLAGS) -c $< -o $@

$(KERNEL): $(OBJ) linker.ld
	$(LD) $(LDFLAGS) $(OBJ) -o $@

run: $(KERNEL)
	qemu-system-i386 -kernel $(KERNEL)

iso: $(KERNEL)
	mkdir -p build/iso/boot/grub
	cp $(KERNEL) build/iso/boot/saskeos.bin
	printf 'set timeout=0\nmenuentry "SaskeOS" {\n  multiboot /boot/saskeos.bin\n}\n' > build/iso/boot/grub/grub.cfg
	grub-mkrescue -o build/saskeos.iso build/iso

clean:
	rm -rf build

.PHONY: all run iso clean
