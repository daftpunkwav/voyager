/*
 * graph_layout / graph-layout-cli: optional C-accelerated layout.
 * Python force_layout_3d is the fallback when this library is absent.
 * Do not confuse with graph-engine from graph_engine_core.
 */
#include <math.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#define GRAPH_LAYOUT_EXPORT __declspec(dllexport)
#else
#define GRAPH_LAYOUT_EXPORT
#endif

typedef struct {
  float x, y, z;
  float size;
  int in_calls;
} LayoutNode;

typedef struct {
  int source;
  int target;
} LayoutEdge;

GRAPH_LAYOUT_EXPORT void graph_layout3d(
    LayoutNode *nodes,
    int n_nodes,
    const LayoutEdge *edges,
    int n_edges,
    int iterations
) {
  if (!nodes || n_nodes <= 0) return;
  if (iterations <= 0) iterations = 40;

  for (int i = 0; i < n_nodes; i++) {
    if (nodes[i].x == 0 && nodes[i].y == 0 && nodes[i].z == 0) {
      float phi = acosf(1.0f - 2.0f * ((float)i + 0.5f) / (float)n_nodes);
      float theta = 3.14159265f * (1.0f + 2.23606797f) * (float)i;
      float r = 40.0f + (n_nodes < 500 ? n_nodes : 500) * 0.05f;
      nodes[i].x = r * sinf(phi) * cosf(theta);
      nodes[i].y = r * sinf(phi) * sinf(theta);
      nodes[i].z = r * cosf(phi);
    }
  }

  float *fx = (float *)calloc((size_t)n_nodes, sizeof(float));
  float *fy = (float *)calloc((size_t)n_nodes, sizeof(float));
  float *fz = (float *)calloc((size_t)n_nodes, sizeof(float));
  if (!fx || !fy || !fz) {
    free(fx); free(fy); free(fz);
    return;
  }

  for (int it = 0; it < iterations; it++) {
    memset(fx, 0, (size_t)n_nodes * sizeof(float));
    memset(fy, 0, (size_t)n_nodes * sizeof(float));
    memset(fz, 0, (size_t)n_nodes * sizeof(float));

    for (int i = 0; i < n_nodes; i++) {
      for (int j = i + 1; j < n_nodes; j++) {
        float dx = nodes[i].x - nodes[j].x;
        float dy = nodes[i].y - nodes[j].y;
        float dz = nodes[i].z - nodes[j].z;
        float dist2 = dx * dx + dy * dy + dz * dz + 0.01f;
        float dist = sqrtf(dist2);
        float force = 80.0f / dist2;
        fx[i] += force * dx / dist;
        fy[i] += force * dy / dist;
        fz[i] += force * dz / dist;
        fx[j] -= force * dx / dist;
        fy[j] -= force * dy / dist;
        fz[j] -= force * dz / dist;
      }
    }

    for (int e = 0; e < n_edges; e++) {
      int i = edges[e].source;
      int j = edges[e].target;
      if (i < 0 || j < 0 || i >= n_nodes || j >= n_nodes) continue;
      float dx = nodes[j].x - nodes[i].x;
      float dy = nodes[j].y - nodes[i].y;
      float dz = nodes[j].z - nodes[i].z;
      float dist = sqrtf(dx * dx + dy * dy + dz * dz) + 0.01f;
      float force = (dist - 12.0f) * 0.02f;
      fx[i] += force * dx / dist;
      fy[i] += force * dy / dist;
      fz[i] += force * dz / dist;
      fx[j] -= force * dx / dist;
      fy[j] -= force * dy / dist;
      fz[j] -= force * dz / dist;
    }

    for (int i = 0; i < n_nodes; i++) {
      fx[i] -= nodes[i].x * 0.01f;
      fy[i] -= nodes[i].y * 0.01f;
      fz[i] -= nodes[i].z * 0.01f;
      float cx = fx[i]; if (cx > 2) cx = 2; if (cx < -2) cx = -2;
      float cy = fy[i]; if (cy > 2) cy = 2; if (cy < -2) cy = -2;
      float cz = fz[i]; if (cz > 2) cz = 2; if (cz < -2) cz = -2;
      nodes[i].x += cx;
      nodes[i].y += cy;
      nodes[i].z += cz;
      float ic = (float)nodes[i].in_calls;
      nodes[i].size = 1.0f + (ic > 0 ? log1pf(ic) * 1.5f : 0.0f);
      if (nodes[i].size > 9.0f) nodes[i].size = 9.0f;
    }
  }

  free(fx); free(fy); free(fz);
}

/* Minimal CLI: graph-layout-cli --version */
#ifdef LAYOUT_CLI
#include <stdio.h>
int main(int argc, char **argv) {
  (void)argc; (void)argv;
  printf("graph-layout-cli 0.1.0\n");
  return 0;
}
#endif
