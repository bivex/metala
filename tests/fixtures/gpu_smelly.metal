#include <metal_stdlib>
using namespace metal;

struct VertexOut {
    float4 pos [[position]];
    float2 uv;
    float3 normal;
    float3 tangent; // Unused in fragment
};

// vertex_output_bloat (heuristic: many fields in stage_out)
vertex VertexOut vertex_main(uint vid [[vertex_id]]) {
    VertexOut out;
    out.pos = float4(0);
    out.uv = float2(0);
    out.normal = float3(0);
    out.tangent = float3(0);
    return out;
}

// half_precision_neglect
fragment float4 fragment_main(VertexOut in [[stage_in]]) {
    float4 color = float4(1, 0, 0, 1); // Should use half4
    float3 normal = normalize(in.normal); // Should use half3
    return color;
}

kernel void compute_smelly(
    device float* buffer [[buffer(0)]],
    uint gid [[thread_position_in_grid]],
    uint tid [[thread_index_in_threadgroup]],
    uint2 grid_pos [[thread_position_in_grid]]
) {
    // excessive_threadgroup_allocation
    threadgroup float expensive_shared[8192]; // 32KB > 16KB threshold
    
    // threadgroup_bank_conflict
    expensive_shared[tid * 16] = 1.0; 
    
    // non_coalesced_access
    buffer[grid_pos.y * 1024 + grid_pos.x] = expensive_shared[tid]; // stride 1024 > 1
    
    // threadgroup_barrier_overuse
    threadgroup_barrier(mem_flags::mem_threadgroup);
    threadgroup_barrier(mem_flags::mem_threadgroup);
    
    // simdgroup_opportunity_missed
    float sum = 0;
    for (int i = 0; i < 32; i++) {
        sum += expensive_shared[i];
    }
    
    // dependent_texture_read (requires texture sample)
    // divergent_texture_sample (requires if(gid) { tex.sample(...) })
}

kernel void divergent_shader(
    texture2d<float> tex [[texture(0)]],
    uint gid [[thread_position_in_grid]]
) {
    constexpr sampler s(filter::linear);
    
    // divergent_branch + divergent_texture_sample
    if (gid > 100) {
        float4 c = tex.sample(s, float2(0.5));
    }
}
