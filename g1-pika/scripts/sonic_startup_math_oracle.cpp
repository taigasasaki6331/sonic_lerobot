// File/stdin-only diagnostic. Equations use pinned Apache-2.0 upstream math_utils.hpp.
// Input: current base, current reference, initial base, initial reference (wxyz).
// Output: plain orientation6, heading-aligned orientation6, gravity3, heading delta4.
#include "math_utils.hpp"
#include <iostream>
#include <iomanip>

int main() {
  std::array<double, 4> base, ref, initial_base, initial_ref;
  std::cout << std::setprecision(17);
  while (std::cin >> base[0] >> base[1] >> base[2] >> base[3]
                  >> ref[0] >> ref[1] >> ref[2] >> ref[3]
                  >> initial_base[0] >> initial_base[1] >> initial_base[2] >> initial_base[3]
                  >> initial_ref[0] >> initial_ref[1] >> initial_ref[2] >> initial_ref[3]) {
    auto delta = quat_mul_d(calc_heading_quat_d(initial_base), calc_heading_quat_inv_d(initial_ref));
    auto plain = quat_to_rotation_matrix_d(quat_mul_d(quat_conjugate_d(base), ref));
    auto aligned = quat_to_rotation_matrix_d(quat_mul_d(quat_conjugate_d(base), quat_mul_d(delta, ref)));
    auto gravity = quat_rotate_d(quat_conjugate_d(base), {0., 0., -1.});
    for (const auto& matrix : {plain, aligned})
      for (int i = 0; i < 3; ++i)
        for (int j = 0; j < 2; ++j) std::cout << matrix[i][j] << ' ';
    for (double value : gravity) std::cout << value << ' ';
    for (double value : delta) std::cout << value << ' ';
    std::cout << '\n';
  }
  return std::cin.eof() ? 0 : 1;
}
