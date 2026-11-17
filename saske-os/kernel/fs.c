#include "kernel.h"

/* RAM-диск: плоский список файлов с данными в куче */
#define MAX_FILES 32
#define NAME_LEN  24

struct file { char name[NAME_LEN]; char *data; size_t len; int used; };
static struct file files[MAX_FILES];

static struct file *find(const char *name) {
    for (int i = 0; i < MAX_FILES; i++)
        if (files[i].used && !strcmp(files[i].name, name)) return &files[i];
    return 0;
}

int fs_write(const char *name, const char *data, int append) {
    if (!*name || strlen(name) >= NAME_LEN) return -1;
    struct file *f = find(name);
    if (!f) {
        for (int i = 0; i < MAX_FILES && !f; i++) if (!files[i].used) f = &files[i];
        if (!f) return -2;
        memset(f, 0, sizeof *f);
        strncpy(f->name, name, NAME_LEN - 1);
        f->used = 1;
        append = 0;
    }
    size_t add = strlen(data);
    size_t keep = append ? f->len : 0;
    char *nd = kmalloc(keep + add + 1);
    if (!nd) return -3;
    if (keep) memcpy(nd, f->data, keep);
    memcpy(nd + keep, data, add + 1);
    kfree(f->data);
    f->data = nd; f->len = keep + add;
    return 0;
}

const char *fs_read(const char *name) { struct file *f = find(name); return f ? f->data : 0; }

int fs_remove(const char *name) {
    struct file *f = find(name);
    if (!f) return -1;
    kfree(f->data);
    f->used = 0;
    return 0;
}

void fs_list(void) {
    int n = 0;
    for (int i = 0; i < MAX_FILES; i++) if (files[i].used) {
        kprintf("  %s", files[i].name);
        for (int p = strlen(files[i].name); p < NAME_LEN; p++) vga_putc(' ');
        kprintf("%u bytes\n", (uint32_t)files[i].len);
        n++;
    }
    if (!n) kprintf("  (empty)\n");
}

void fs_init(void) {
    fs_write("readme.txt",
        "Welcome to SaskeOS!\n"
        "This is a tiny 32-bit x86 operating system written from scratch.\n"
        "Files live in RAM and disappear on reboot.\n"
        "Type 'help' to see what you can do.\n", 0);
    fs_write("motd.txt", "Have a nice day :)\n", 0);
}
