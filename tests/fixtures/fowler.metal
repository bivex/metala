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
// 7. Feature Envy (interested in other object)
// 8. Middle Man (only delegates)
// 9. Shotgun Surgery (touches many objects)
struct Manager {
    Derived d;
    
    void delegate_call() {
        // Message Chain
        int val = d.p1 + d.p2 + d.p3 + d.p4; 
        // Feature Envy (many accesses to 'd')
        int complex = d.p1 * d.p2 * d.p3 * d.p4 * d.p5;
    }
    
    void chain() {
        // Long chain
        // Manager m; m.d.p1;
    }
};

void shotgun(Base b, Derived d, Manager m, int x) {
    // Touching many objects
    b.value = x;
    d.p1 = x;
    m.d.p1 = x;
    int y = x + 1;
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
