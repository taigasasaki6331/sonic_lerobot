#include <assert.h>
#include "sample_clock.h"
int main(void) {
  double deadline=next_sample_deadline(0,100.);
  assert(fabs(deadline-100.02)<1e-9);
  deadline=next_sample_deadline(deadline,100.0205);
  assert(fabs(deadline-100.04)<1e-9);
  assert(100.0403>=deadline); // No accumulation of the previous polling delay.
  deadline=next_sample_deadline(deadline,100.0403);
  assert(fabs(deadline-100.06)<1e-9);
  deadline=next_sample_deadline(deadline,100.125);
  assert(fabs(deadline-100.14)<1e-9); // Never invent the missing real samples.
  return 0;
}
