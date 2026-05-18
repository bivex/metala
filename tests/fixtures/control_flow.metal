#include <metal_stdlib>
using namespace metal;

int score(device const int* values, int count) {
    int total = 0;

    for (int i = 0; i < count; i++) {
        if (values[i] > 0) {
            total = total + values[i];
        } else {
            continue;
        }
    }

    while (total > 100) {
        total = total - 10;
    }

    do {
        total = total - 1;
    } while (total > 50);

    switch (total) {
    case 0:
        return 0;
    case 1:
        return 1;
    default:
        return total;
    }
}

struct MathBox {
    static int normalize(int input) {
        if (input < 0) {
            return 0;
        }
        return input;
    }
};
