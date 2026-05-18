#include <metal_stdlib>
using namespace metal;

struct Base {
    int value;
};

// 1. Refused Bequest (inheriting but might not use members)
// 2. Primitive Obsession (too many primitives)
struct Derived : Base {
    int p1;
    int p2;
    int p3;
    int p4;
    int p5;
    int get_val() { return p1; }
};

// 3. Speculative Generality (declaration without body)
void unused_function_decl(int x);

// 4. Data Clump (same 3+ params in multiple functions)
void process_coords(float x, float y, float z) {
}

void render_at(float x, float y, float z, int color) {
}

// 5. Switch Statement
void handle_type(int type) {
    switch (type) {
        case 0: break;
        case 1: break;
    }
}

// 6. Message Chain (a.b.c.d)
struct S4 { int val; };
struct S3 { S4 s4; };
struct S2 { S3 s3; };
struct S1 { S2 s2; };

void chain_func(S1 s1) {
    int x = s1.s2.s3.s4.val; // length 4 > 3
}

// 7. Feature Envy (interested in other object)
// 8. Middle Man (only delegates)
struct Manager {
    Derived d;
    
    void delegate_call() {
        // Envy d's data
        int complex = d.p1 * d.p2 * d.p3 * d.p4 * d.p5;
    }
    
    void middle_man_func() {
        // Middle Man: only calls one function
        d.get_val();
    }
};

// 7. Feature Envy (Better example: top level function envying 'd')
void envy_function(Derived d) {
    int x = d.p1 + d.p2 + d.p3 + d.p4 + d.p5;
}

// 9. Shotgun Surgery (touches many objects)
void shotgun(Base b, Derived d, Manager m, int x) {
    // Touching 4 different types of objects
    b.value = x;
    d.p1 = x;
    m.d.p1 = x;
    int y = x;
}

// 10. Temporary Field
struct Temp {
    void func() {
        int temp_var = 10; // Declared in function
    }
};

// 11. Comment Density
// This function has too many comments
// Deodorant comment 1
// Deodorant comment 2
// Deodorant comment 3
// Deodorant comment 4
// Deodorant comment 5
// Deodorant comment 6
// Deodorant comment 7
// Deodorant comment 8
// Deodorant comment 9
// Deodorant comment 10
// Deodorant comment 11
// Deodorant comment 12
// Deodorant comment 13
// Deodorant comment 14
// Deodorant comment 15
// Deodorant comment 16
// Deodorant comment 17
// Deodorant comment 18
// Deodorant comment 19
// Deodorant comment 20
// Deodorant comment 21
// Deodorant comment 22
// Deodorant comment 23
// Deodorant comment 24
// Deodorant comment 25
// Deodorant comment 26
// Deodorant comment 27
// Deodorant comment 28
// Deodorant comment 29
// Deodorant comment 30
// Deodorant comment 31
// Deodorant comment 32
// Deodorant comment 33
// Deodorant comment 34
// Deodorant comment 35
// Deodorant comment 36
// Deodorant comment 37
// Deodorant comment 38
// Deodorant comment 39
// Deodorant comment 40
// Deodorant comment 41
// Deodorant comment 42
// Deodorant comment 43
// Deodorant comment 44
// Deodorant comment 45
// Deodorant comment 46
// Deodorant comment 47
// Deodorant comment 48
// Deodorant comment 49
// Deodorant comment 50
// Deodorant comment 51
// Deodorant comment 52
// Deodorant comment 53
// Deodorant comment 54
// Deodorant comment 55
// Deodorant comment 56
// Deodorant comment 57
// Deodorant comment 58
// Deodorant comment 59
// Deodorant comment 60
// Deodorant comment 61
// Deodorant comment 62
// Deodorant comment 63
// Deodorant comment 64
// Deodorant comment 65
// Deodorant comment 66
// Deodorant comment 67
// Deodorant comment 68
// Deodorant comment 69
// Deodorant comment 70
// Deodorant comment 71
// Deodorant comment 72
// Deodorant comment 73
// Deodorant comment 74
// Deodorant comment 75
// Deodorant comment 76
// Deodorant comment 77
// Deodorant comment 78
// Deodorant comment 79
// Deodorant comment 80
// Deodorant comment 81
// Deodorant comment 82
// Deodorant comment 83
// Deodorant comment 84
// Deodorant comment 85
// Deodorant comment 86
// Deodorant comment 87
// Deodorant comment 88
// Deodorant comment 89
// Deodorant comment 90
// Deodorant comment 91
// Deodorant comment 92
// Deodorant comment 93
// Deodorant comment 94
// Deodorant comment 95
// Deodorant comment 96
// Deodorant comment 97
// Deodorant comment 98
// Deodorant comment 99
// Deodorant comment 100
void complex_logic() {
    int x = 0;
}

// 12. Divergent Change (simulated by many member functions)
struct GodObject {
    void f1() {}
    void f2() {}
    void f3() {}
    void f4() {}
    void f5() {}
    void f6() {}
    void f7() {}
    void f8() {}
    void f9() {}
    void f10() {}
    void f11() {}
};
