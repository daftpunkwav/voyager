#ifndef ENGINE_LZ4_STORE_H
#define ENGINE_LZ4_STORE_H

// LZ4 HC compression (level 9).
int engine_lz4_compress_hc(const char *src, int srcLen, char *dst, int dstCap);

// LZ4 decompression.
int engine_lz4_decompress(const char *src, int srcLen, char *dst, int originalLen);

// Maximum compressed size bound.
int engine_lz4_bound(int inputSize);

#endif // ENGINE_LZ4_STORE_H
