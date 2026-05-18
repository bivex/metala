#include <metal_stdlib>
using namespace metal;

[[kernel]] void divergent_kernel(
    uint gid [[thread_position_in_grid]],
    device int* data [[buffer(0)]],
    device int* out [[buffer(1)]]
) {
    // 21. Divergent Branch
    if (gid % 2 == 0) {
        out[gid] = data[gid] * 2;
    }
    
    // 22. Resource Overload (> 8 resources)
}

void overload(
    texture2d<float> t1 [[texture(0)]],
    texture2d<float> t2 [[texture(1)]],
    texture2d<float> t3 [[texture(2)]],
    texture2d<float> t4 [[texture(3)]],
    texture2d<float> t5 [[texture(4)]],
    texture2d<float> t6 [[texture(5)]],
    texture2d<float> t7 [[texture(6)]],
    texture2d<float> t8 [[texture(7)]],
    texture2d<float> t9 [[texture(8)]],
    device int* b1 [[buffer(0)]]
) {
}

// 23. Atomic Contention
void contention(device atomic_int* a) {
    for (int i = 0; i < 100; i++) {
        atomic_fetch_add_explicit(a, 1, memory_order_relaxed);
        atomic_fetch_sub_explicit(a, 1, memory_order_relaxed);
        atomic_exchange_explicit(a, 0, memory_order_relaxed);
    }
}
