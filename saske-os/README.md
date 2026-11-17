# SaskeOS

Маленькая 32-битная операционная система для x86, написанная с нуля на C и NASM.

## Что умеет

- Загрузка по стандарту **Multiboot** (GRUB или `qemu -kernel`)
- Защищённый режим, своя **GDT** и **IDT**
- Перенастройка контроллера прерываний **PIC**, обработка исключений CPU (экран «kernel panic»)
- Системный таймер **PIT** на 100 Гц: `uptime`, `sleep`
- Драйвер **PS/2-клавиатуры** (Shift, Caps Lock, Ctrl+L)
- **VGA**-консоль 80×25 с цветом, прокруткой и курсором; вывод дублируется в COM1
- **Куча** (`kmalloc`/`kfree`) со слиянием свободных блоков
- **Файловая система в RAM**: `ls`, `cat`, `write`, `append`, `rm`
- **Командная оболочка**: `help`, `echo`, `calc`, `mem`, `color`, `guess` (игра), `reboot`, `halt`

## Сборка и запуск

Нужны `gcc` (с поддержкой `-m32`), `nasm`, `ld` и `qemu-system-i386`:

```sh
sudo apt install build-essential gcc-multilib nasm qemu-system-x86
make run
```

Загрузочный ISO (для VirtualBox или флешки) — нужны `grub-pc-bin` и `xorriso`:

```sh
make iso      # build/saskeos.iso
```

## Устройство

| Файл | Назначение |
|---|---|
| `boot/boot.asm` | Multiboot-заголовок, стек, вход в ядро, заглушки прерываний |
| `kernel/kernel.c` | `kernel_main`: инициализация всех подсистем |
| `kernel/idt.c` | GDT, IDT, PIC, диспетчер прерываний и исключений |
| `kernel/vga.c` | Текстовый экран и `kprintf` |
| `kernel/timer.c` | Таймер PIT |
| `kernel/keyboard.c` | Клавиатура PS/2 |
| `kernel/mem.c` | Куча |
| `kernel/fs.c` | Файловая система в памяти |
| `kernel/shell.c` | Оболочка |
| `linker.ld` | Ядро грузится по адресу 1 МБ |
