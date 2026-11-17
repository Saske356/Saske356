; SaskeOS — точка входа (Multiboot 1)
MB_MAGIC    equ 0x1BADB002
MB_FLAGS    equ (1 << 0) | (1 << 1)         ; выравнивание модулей + карта памяти
MB_CHECKSUM equ -(MB_MAGIC + MB_FLAGS)

section .multiboot
align 4
    dd MB_MAGIC
    dd MB_FLAGS
    dd MB_CHECKSUM

section .bss
align 16
stack_bottom:
    resb 16384
stack_top:

section .text
global _start
extern kernel_main
_start:
    cli
    mov esp, stack_top
    push ebx                ; указатель на multiboot info
    push eax                ; магическое число загрузчика
    call kernel_main
.hang:
    cli
    hlt
    jmp .hang

; ---------- GDT ----------
global gdt_flush
gdt_flush:
    mov eax, [esp + 4]
    lgdt [eax]
    mov ax, 0x10
    mov ds, ax
    mov es, ax
    mov fs, ax
    mov gs, ax
    mov ss, ax
    jmp 0x08:.flush
.flush:
    ret

global idt_load
idt_load:
    mov eax, [esp + 4]
    lidt [eax]
    ret

; ---------- Обработчики прерываний ----------
%macro ISR_NOERR 1
global isr%1
isr%1:
    push dword 0
    push dword %1
    jmp common_stub
%endmacro

%macro ISR_ERR 1
global isr%1
isr%1:
    push dword %1
    jmp common_stub
%endmacro

%macro IRQ 2
global irq%1
irq%1:
    push dword 0
    push dword %2
    jmp common_stub
%endmacro

ISR_NOERR 0
ISR_NOERR 1
ISR_NOERR 2
ISR_NOERR 3
ISR_NOERR 4
ISR_NOERR 5
ISR_NOERR 6
ISR_NOERR 7
ISR_ERR   8
ISR_NOERR 9
ISR_ERR   10
ISR_ERR   11
ISR_ERR   12
ISR_ERR   13
ISR_ERR   14
ISR_NOERR 15
ISR_NOERR 16
ISR_ERR   17
ISR_NOERR 18
ISR_NOERR 19
ISR_NOERR 20
ISR_NOERR 21
ISR_NOERR 22
ISR_NOERR 23
ISR_NOERR 24
ISR_NOERR 25
ISR_NOERR 26
ISR_NOERR 27
ISR_NOERR 28
ISR_NOERR 29
ISR_ERR   30
ISR_NOERR 31

%assign i 0
%rep 16
IRQ i, i+32
%assign i i+1
%endrep

extern interrupt_handler
common_stub:
    pusha
    push ds
    push es
    push fs
    push gs
    mov ax, 0x10
    mov ds, ax
    mov es, ax
    mov fs, ax
    mov gs, ax
    push esp                ; struct regs*
    call interrupt_handler
    add esp, 4
    pop gs
    pop fs
    pop es
    pop ds
    popa
    add esp, 8              ; номер прерывания + код ошибки
    iret
