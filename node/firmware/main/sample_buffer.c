#include "sample_buffer.h"

void sb_init(sample_buffer_t *b, sample_t *storage, int capacity)
{
    b->items = storage;
    b->capacity = capacity;
    b->head = 0;
    b->count = 0;
    b->dropped = 0;
}

void sb_push(sample_buffer_t *b, const sample_t *s)
{
    if (b->count == b->capacity) {
        b->head = (b->head + 1) % b->capacity;
        b->count--;
        b->dropped++;
    }
    b->items[(b->head + b->count) % b->capacity] = *s;
    b->count++;
}

int sb_peek(const sample_buffer_t *b, sample_t *out)
{
    if (b->count == 0) return 0;
    *out = b->items[b->head];
    return 1;
}

void sb_pop(sample_buffer_t *b)
{
    if (b->count == 0) return;
    b->head = (b->head + 1) % b->capacity;
    b->count--;
}
