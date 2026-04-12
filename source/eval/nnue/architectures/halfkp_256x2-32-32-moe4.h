// Definition of input features and network structure used in NNUE evaluation function
// NNUE評価関数で用いる入力特徴量とネットワーク構造の定義
#ifndef CLASSIC_NNUE_HALFKP_256X2_32_32_MOE4_H_INCLUDED
#define CLASSIC_NNUE_HALFKP_256X2_32_32_MOE4_H_INCLUDED

#include "../features/feature_set.h"
#include "../features/half_kp.h"

#include "../layers/input_slice.h"
#include "../layers/affine_transform_explicit.h"
#include "../layers/affine_transform_sparse_input_explicit.h"
#include "../layers/clipped_relu_explicit.h"

namespace YaneuraOu {
namespace Eval::NNUE {

using RawFeatures = Features::FeatureSet<
    Features::HalfKP<Features::Side::kFriend>>;

constexpr IndexType kTransformedFeatureDimensions = 256;
constexpr int LayerStacks = 4;
constexpr std::uint32_t MoEHashSeed = 0x94A3EDE7u;

namespace Layers {

using InputLayer = InputSlice<kTransformedFeatureDimensions * 2>;
using Router = AffineTransformExplicit<kTransformedFeatureDimensions * 2, LayerStacks>;
using L1 = AffineTransformSparseInputExplicit<kTransformedFeatureDimensions * 2, 32>;
using A1 = ClippedReLUExplicit<32>;
using L2 = AffineTransformExplicit<32, 32>;
using A2 = ClippedReLUExplicit<32>;
using L3 = AffineTransformExplicit<32, 1>;

}  // namespace Layers

struct Network {
    Layers::Router router;
    Layers::L1 fc_0[LayerStacks];
    Layers::L2 fc_1;
    Layers::L3 fc_2;

    using OutputType = std::int32_t;
    static constexpr IndexType kOutputDimensions = 1;

    static constexpr std::uint32_t AffineHashValue(std::uint32_t prev_hash, IndexType out_dims) {
        std::uint32_t hash_value = 0xCC03DAE4u;
        hash_value += out_dims;
        hash_value ^= prev_hash >> 1;
        hash_value ^= prev_hash << 31;
        return hash_value;
    }

    static constexpr std::uint32_t MoEHashValue(std::uint32_t prev_hash) {
        std::uint32_t hash_value = MoEHashSeed;
        hash_value += LayerStacks;
        hash_value ^= prev_hash >> 1;
        hash_value ^= prev_hash << 31;
        return AffineHashValue(hash_value, 32);
    }

    static constexpr std::uint32_t GetHashValue() {
        auto hash_value = AffineHashValue(Layers::InputLayer::GetHashValue(), LayerStacks);
        hash_value = MoEHashValue(hash_value);
        hash_value = Layers::L2::GetHashValue(Layers::A1::GetHashValue(hash_value));
        hash_value = Layers::L3::GetHashValue(Layers::A2::GetHashValue(hash_value));
        return hash_value;
    }

    static std::string GetStructureString() {
        return "AffineTransform[1<-32](ClippedReLU[32](AffineTransform[32<-32]"
            "(ClippedReLU[32](MoE[4x32<-512](AffineTransform[4<-512](InputSlice[512(0:512)]))))))";
    }

    struct alignas(kCacheLineSize) Buffer {
        alignas(kCacheLineSize) typename Layers::Router::OutputBuffer router_out;
        alignas(kCacheLineSize) typename Layers::L1::OutputBuffer fc_0_out;
        alignas(kCacheLineSize) typename Layers::A1::OutputBuffer ac_0_out;
        alignas(kCacheLineSize) typename Layers::L2::OutputBuffer fc_1_out;
        alignas(kCacheLineSize) typename Layers::A2::OutputBuffer ac_1_out;
        alignas(kCacheLineSize) typename Layers::L3::OutputBuffer fc_2_out;
    };

    static constexpr std::size_t kBufferSize = sizeof(Buffer);

    int SelectExpert(const TransformedFeatureType* transformedFeatures, char* buffer) const {
        auto& buf = *reinterpret_cast<Buffer*>(buffer);
        router.Propagate(transformedFeatures, buf.router_out);

        int best = 0;
        auto best_score = buf.router_out[0];
        for (int i = 1; i < LayerStacks; ++i) {
            if (buf.router_out[i] > best_score) {
                best_score = buf.router_out[i];
                best = i;
            }
        }
        return best;
    }

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

#endif // #ifndef CLASSIC_NNUE_HALFKP_256X2_32_32_MOE4_H_INCLUDED
