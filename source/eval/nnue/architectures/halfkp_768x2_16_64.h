// Definition of input features and network structure used in NNUE evaluation function
// NNUE評価関数で用いる入力特徴量とネットワーク構造の定義
#ifndef CLASSIC_NNUE_HALFKP_768X2_16_64_H_INCLUDED
#define CLASSIC_NNUE_HALFKP_768X2_16_64_H_INCLUDED

#include "../features/feature_set.h"
#include "../features/half_kp.h"

#include "../layers/input_slice.h"
#include "../layers/affine_transform_explicit.h"
#include "../layers/affine_transform_sparse_input_explicit.h"
#include "../layers/clipped_relu_explicit.h"

namespace YaneuraOu {
namespace Eval::NNUE {

// Input features used in evaluation function
// 評価関数で用いる入力特徴量
using RawFeatures = Features::FeatureSet<
    Features::HalfKP<Features::Side::kFriend>>;

// Number of input feature dimensions after conversion
// 変換後の入力特徴量の次元数
constexpr IndexType kTransformedFeatureDimensions = 768;

// Number of networks stored in the evaluation file
constexpr int LayerStacks = 8;

namespace Layers {

using InputLayer = InputSlice<kTransformedFeatureDimensions * 2>;
using L1 = AffineTransformSparseInputExplicit<kTransformedFeatureDimensions * 2, 16>;
using A1 = ClippedReLUExplicit<16>;
using L2 = AffineTransformExplicit<16, 64>;
using A2 = ClippedReLUExplicit<64>;
using L3 = AffineTransformExplicit<64, 1>;

}  // namespace Layers

struct Network {
    // ネットワーク構造の定義
    // 仕様に基づき L1 (fc_0) のみをスタック化する
    Layers::L1 fc_0[LayerStacks];
    Layers::L2 fc_1;
    Layers::L3 fc_2;

    using OutputType = std::int32_t;
    static constexpr IndexType kOutputDimensions = 1;

    static constexpr std::uint32_t LayerStackHashValue(std::uint32_t prev_hash) {
        std::uint32_t hash_value = 0xB58B6A8Du;
        hash_value += LayerStacks;
        hash_value ^= prev_hash >> 1;
        hash_value ^= prev_hash << 31;
        return hash_value;
    }

    static constexpr std::uint32_t GetHashValue() {
        auto hash_value = LayerStackHashValue(Layers::InputLayer::GetHashValue());
        hash_value = Layers::L2::GetHashValue(Layers::A1::GetHashValue(hash_value));
        hash_value = Layers::L3::GetHashValue(Layers::A2::GetHashValue(hash_value));
        return hash_value;
    }

    static std::string GetStructureString() {
        return "AffineTransform[1<-64](ClippedReLU[64](AffineTransform[64<-16]"
            "(ClippedReLU[16](LayerStack[8x16<-1536](InputSlice[1536(0:1536)])))))";
    }

    struct alignas(kCacheLineSize) Buffer {
        alignas(kCacheLineSize) typename Layers::L1::OutputBuffer fc_0_out;
        alignas(kCacheLineSize) typename Layers::A1::OutputBuffer ac_0_out;
        alignas(kCacheLineSize) typename Layers::L2::OutputBuffer fc_1_out;
        alignas(kCacheLineSize) typename Layers::A2::OutputBuffer ac_1_out;
        alignas(kCacheLineSize) typename Layers::L3::OutputBuffer fc_2_out;
    };

    static constexpr std::size_t kBufferSize = sizeof(Buffer);

    const OutputType* Propagate(const TransformedFeatureType* transformedFeatures, char* buffer, int bucket = 0) const {
        auto& buf = *reinterpret_cast<Buffer*>(buffer);

        fc_0[bucket].Propagate(transformedFeatures, buf.fc_0_out);
        Layers::A1 ac_0;
        ac_0.Propagate(buf.fc_0_out, buf.ac_0_out);
        fc_1.Propagate(buf.ac_0_out, buf.fc_1_out);
        Layers::A2 ac_1;
        ac_1.Propagate(buf.fc_1_out, buf.ac_1_out);
        fc_2.Propagate(buf.ac_1_out, buf.fc_2_out);

        return buf.fc_2_out;
    }
};

}  // namespace Eval::NNUE

} // namespace YaneuraOu

#endif // #ifndef CLASSIC_NNUE_HALFKP_768X2_16_64_H_INCLUDED
