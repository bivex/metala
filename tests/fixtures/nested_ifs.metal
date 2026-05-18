#include <metal_stdlib>
using namespace metal;

// Deeply nested if-else demo — demonstrates depth badges & color cycling
int processRegion(int value) {
    if (value > 0) {
        if (value > 50) {
            if (value > 90) {
                if (value > 120) {
                    return 4;
                } else {
                    return 3;
                }
            } else {
                if (value > 70) {
                    return 2;
                } else {
                    return 1;
                }
            }
        } else {
            if (value > 25) {
                return 1;
            } else {
                return 0;
            }
        }
    } else {
        return -1;
    }
}
