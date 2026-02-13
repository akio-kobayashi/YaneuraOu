#!/bin/bash
set -e

# --- Configuration ---
# ビルドディレクトリ
BUILD_DIR="build"

# --- Build Process ---
echo "--- Creating build directory ---"
mkdir -p $BUILD_DIR
cd $BUILD_DIR

echo "--- Running CMake ---"
# CMAKE_ARGS="-DCMAKE_BUILD_TYPE=Release"
# For debugging, use:
CMAKE_ARGS="-DCMAKE_BUILD_TYPE=Debug"
cmake .. ${CMAKE_ARGS}

echo "--- Running Make ---"
# Use all available cores for building
make -j$(nproc 2>/dev/null || sysctl -n hw.ncpu)

echo "--- Build complete ---"
echo "The shared library is located in:"
echo "$(pwd)/yaneuraou_wrapper.cpython-*.so"
echo ""
echo "You can test it by running python from the 'yaneuraou_python_wrapper' directory."

cd ..

# Copy the built file to the yaneuraou_python_wrapper directory so it can be imported.
# The exact name depends on the Python version.
find $BUILD_DIR -name "*.so" -exec cp {} ./yaneuraou_python_wrapper/ \;
echo "Copied .so file to yaneuraou_python_wrapper/ directory."
