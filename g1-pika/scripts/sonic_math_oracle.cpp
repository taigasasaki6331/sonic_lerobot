// File/stdin-only comparison oracle using pinned upstream quaternion functions.
#include "math_utils.hpp"
#include <iostream>
#include <iomanip>
int main() {
  std::array<double,4> base,ref;
  std::cout<<std::setprecision(17);
  while(std::cin>>base[0]>>base[1]>>base[2]>>base[3]
                 >>ref[0]>>ref[1]>>ref[2]>>ref[3]) {
    auto r=quat_to_rotation_matrix_d(quat_mul_d(quat_conjugate_d(base),ref));
    auto g=quat_rotate_d(quat_conjugate_d(base),{0.,0.,-1.});
    for(int i=0;i<3;i++) for(int j=0;j<2;j++) std::cout<<r[i][j]<<' ';
    for(double x:g) std::cout<<x<<' ';
    std::cout<<'\n';
  }
  return std::cin.eof()?0:1;
}
