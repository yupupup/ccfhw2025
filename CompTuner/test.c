#include <stdio.h>
#include <stdlib.h>

#define N 2000
#define ITER 50

static double A[N][N];
static double B[N][N];
static double C[N][N];

/* 初始化矩阵 */
void init_matrix() {
    for (int i = 0; i < N; i++) {
        for (int j = 0; j < N; j++) {
            A[i][j] = (i + j) * 0.001;
            B[i][j] = (i - j) * 0.002;
            C[i][j] = 0.0;
        }
    }
}

/* 核心计算：矩阵计算 + 分支 */
void compute() {
    for (int iter = 0; iter < ITER; iter++) {
        for (int i = 0; i < N; i++) {
            for (int j = 0; j < N; j++) {
                double v = A[i][j] * B[j][i];
                if (v > 0.0) {
                    C[i][j] += v;
                } else {
                    C[i][j] -= v;
                }
            }
        }
    }
}

/* 防止编译器把计算整体优化掉 */
double checksum() {
    double sum = 0.0;
    for (int i = 0; i < N; i++) {
        for (int j = 0; j < N; j++) {
            sum += C[i][j];
        }
    }
    return sum;
}

int main() {
    init_matrix();
    compute();
    printf("Checksum: %.6f\n", checksum());
    return 0;
}
