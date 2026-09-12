cmake_minimum_required(VERSION 3.16)
project(graph_layout C)

set(CMAKE_C_STANDARD 11)

add_library(graph_layout SHARED layout3d.c)
target_include_directories(graph_layout PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
if(WIN32)
  set_target_properties(graph_layout PROPERTIES PREFIX "" OUTPUT_NAME "graph_layout")
endif()

# Layout acceleration CLI; do not confuse it with graph-engine, the MCP
# indexing engine in graph_engine_core
add_executable(graph-layout-cli layout3d.c)
target_compile_definitions(graph-layout-cli PRIVATE LAYOUT_CLI=1)

install(TARGETS graph_layout graph-layout-cli
  RUNTIME DESTINATION bin
  LIBRARY DESTINATION lib
  ARCHIVE DESTINATION lib
)
