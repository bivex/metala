#include <metal_stdlib>
using namespace metal;

struct Vertex {
    float4 position [[position]];
    float4 color;
};

struct Uniforms {
    float4x4 modelViewProjection;
};

vertex Vertex main_vertex(device const Vertex* vertices [[buffer(0)]],
                          constant Uniforms& uniforms [[buffer(1)]],
                          uint vid [[vertex_id]]) {
    Vertex out;
    out.position = uniforms.modelViewProjection * vertices[vid].position;
    out.color = vertices[vid].color;
    return out;
}

fragment float4 main_fragment(Vertex in [[stage_in]]) {
    return in.color;
}
