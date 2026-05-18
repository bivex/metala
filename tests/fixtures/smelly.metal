#include <metal_stdlib>
using namespace metal;

// Long Parameter List Smell (> 5 parameters)
// and Unused Parameter Smell
void long_parameter_function(
    int p1, int p2, int p3, int p4, int p5, int p6
) {
    // Only p1 is used
    int x = p1;
}

// Deep Nesting Smell (> 3 levels)
void deep_nesting_function() {
    if (true) {
        if (true) {
            if (true) {
                if (true) {
                    // Level 4
                }
            }
        }
    }
}

// Complex Flow Smell (CC > 10)
void complex_flow_function(int x) {
    if (x == 1) {}
    if (x == 2) {}
    if (x == 3) {}
    if (x == 4) {}
    if (x == 5) {}
    if (x == 6) {}
    if (x == 7) {}
    if (x == 8) {}
    if (x == 9) {}
    if (x == 10) {}
    // CC will be 11
}

// Excessive Locals Smell (> 10)
void excessive_locals_function() {
    int v1, v2, v3, v4, v5, v6, v7, v8, v9, v10, v11;
}

// Magic Number Smell
void magic_number_function(float r) {
    // 3.14 is a magic number
    float area = 3.14 * r * r;
    // 123.45 is a magic number
    float volume = 123.45 * r;
    
    // NOT a magic number (ignored values)
    float x = 1.0;
    float y = 0;
    
    // NOT a magic number (constant definition)
    const float MY_PI = 3.14159;
}

// Long Function Smell (> 50 lines)
void long_function() {
    // 1
    // 2
    // 3
    // 4
    // 5
    // 6
    // 7
    // 8
    // 9
    // 10
    // 11
    // 12
    // 13
    // 14
    // 15
    // 16
    // 17
    // 18
    // 19
    // 20
    // 21
    // 22
    // 23
    // 24
    // 25
    // 26
    // 27
    // 28
    // 29
    // 30
    // 31
    // 32
    // 33
    // 34
    // 35
    // 36
    // 37
    // 38
    // 39
    // 40
    // 41
    // 42
    // 43
    // 44
    // 45
    // 46
    // 47
    // 48
    // 49
    // 50
    // 51
}

// Large Class Smell (> 200 lines)
struct LargeStruct {
    int x1;
    int x2;
    int x3;
    int x4;
    int x5;
    int x6;
    int x7;
    int x8;
    int x9;
    int x10;
    int x11;
    int x12;
    int x13;
    int x14;
    int x15;
    int x16;
    int x17;
    int x18;
    int x19;
    int x20;
    int x21;
    int x22;
    int x23;
    int x24;
    int x25;
    int x26;
    int x27;
    int x28;
    int x29;
    int x30;
    int x31;
    int x32;
    int x33;
    int x34;
    int x35;
    int x36;
    int x37;
    int x38;
    int x39;
    int x40;
    int x41;
    int x42;
    int x43;
    int x44;
    int x45;
    int x46;
    int x47;
    int x48;
    int x49;
    int x50;
    int x51;
    int x52;
    int x53;
    int x54;
    int x55;
    int x56;
    int x57;
    int x58;
    int x59;
    int x60;
    int x61;
    int x62;
    int x63;
    int x64;
    int x65;
    int x66;
    int x67;
    int x68;
    int x69;
    int x70;
    int x71;
    int x72;
    int x73;
    int x74;
    int x75;
    int x76;
    int x77;
    int x78;
    int x79;
    int x80;
    int x81;
    int x82;
    int x83;
    int x84;
    int x85;
    int x86;
    int x87;
    int x88;
    int x89;
    int x90;
    int x91;
    int x92;
    int x93;
    int x94;
    int x95;
    int x96;
    int x97;
    int x98;
    int x99;
    int x100;
    int x101;
    int x102;
    int x103;
    int x104;
    int x105;
    int x106;
    int x107;
    int x108;
    int x109;
    int x110;
    int x111;
    int x112;
    int x113;
    int x114;
    int x115;
    int x116;
    int x117;
    int x118;
    int x119;
    int x120;
    int x121;
    int x122;
    int x123;
    int x124;
    int x125;
    int x126;
    int x127;
    int x128;
    int x129;
    int x130;
    int x131;
    int x132;
    int x133;
    int x134;
    int x135;
    int x136;
    int x137;
    int x138;
    int x139;
    int x140;
    int x141;
    int x142;
    int x143;
    int x144;
    int x145;
    int x146;
    int x147;
    int x148;
    int x149;
    int x150;
    int x151;
    int x152;
    int x153;
    int x154;
    int x155;
    int x156;
    int x157;
    int x158;
    int x159;
    int x160;
    int x161;
    int x162;
    int x163;
    int x164;
    int x165;
    int x166;
    int x167;
    int x168;
    int x169;
    int x170;
    int x171;
    int x172;
    int x173;
    int x174;
    int x175;
    int x176;
    int x177;
    int x178;
    int x179;
    int x180;
    int x181;
    int x182;
    int x183;
    int x184;
    int x185;
    int x186;
    int x187;
    int x188;
    int x189;
    int x190;
    int x191;
    int x192;
    int x193;
    int x194;
    int x195;
    int x196;
    int x197;
    int x198;
    int x199;
    int x200;
    int x201;
};
