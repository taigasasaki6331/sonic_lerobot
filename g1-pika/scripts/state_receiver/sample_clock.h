// Advance nominal 50Hz phase without fabricating receive timestamps/samples.
// Missed slots are skipped, not filled. Downstream gap checks remain mandatory.
#include <math.h>
static double next_sample_deadline(double deadline, double received) {
  if (deadline == 0) return received + .02;
  return deadline + (floor((received - deadline) / .02) + 1) * .02;
}
