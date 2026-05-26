// Definition of input features and network structure used in NNUE evaluation function
// NNUE評価関数で用いる入力特徴量とネットワーク構造の定義
#ifndef CLASSIC_NNUE_HALFKP_768X2_16_64_H_INCLUDED
#define CLASSIC_NNUE_HALFKP_768X2_16_64_H_INCLUDED

#include "../features/feature_set.h"
#include "../features/half_kp.h"

#include "../layers/input_slice.h"
#include "../layers/affine_transform.h"
#include "../layers/affine_transform_sparse_input.h"
#include "../layers/clipped_relu.h"

namespace YaneuraOu {
namespace Eval::NNUE {

using RawFeatures = Features::FeatureSet<
    Features::HalfKP<Features::Side::kFriend>>;

// Number of input feature dimensions after conversion
// 変換後の入力特徴量の次元数
constexpr IndexType kTransformedFeatureDimensions = 768;

constexpr int LayerStacks = 1;

namespace Layers {

using InputLayer = InputSlice<kTransformedFeatureDimensions * 2>;
using HiddenLayer1 = ClippedReLU<AffineTransformSparseInput<InputLayer, 16>>;
using HiddenLayer2 = ClippedReLU<AffineTransform<HiddenLayer1, 64>>;
using OutputLayer = AffineTransform<HiddenLayer2, 1>;

}  // namespace Layers

struct Network {
    // ネットワーク構造の定義
    using fc0_t = Layers::HiddenLayer1;
    using fc1_t = Layers::HiddenLayer2;
    using fc2_t = Layers::OutputLayer;

    fc0_t fc_0[1];
    fc1_t fc_1;
    fc2_t fc_2;

    using OutputType = std::int32_t;
    static constexpr IndexType kOutputDimensions = 1;

    static constexpr std::uint32_t GetHashValue() {
        auto hash_value = Layers::InputLayer::GetHashValue();
        hash_value = Layers::HiddenLayer1::GetHashValue(hash_value);
        hash_value = Layers::HiddenLayer2::GetHashValue(hash_value);
        hash_value = Layers::OutputLayer::GetHashValue(hash_value);
        return hash_value;
    }

    static std::string GetStructureString() {
        return "AffineTransformSparseInput[64<-1536](ClippedReLU[64]"
            "(AffineTransformSparseInput[1536<-1536](InputSlice[1536(0:1536)])))))";
    }

    static constexpr std::size_t kBufferSize = Layers::OutputLayer::kBufferSize;

    const OutputType* Propagate(
        const TransformedFeatureType* transformed_features,
        char* buffer,
        int /*bucket*/ = 0) const
    {
        return fc_2.Propagate(transformed_features, buffer);
    }

    Tools::Result ReadParameters(std::istream& stream) {
        if (!fc_0[0].ReadParameters(stream).is_ok()) return Tools::ResultCode::FileReadError;
        if (!fc_1.ReadParameters(stream).is_ok()) return Tools::ResultCode::FileReadError;
        if (!fc_2.ReadParameters(stream).is_ok()) return Tools::ResultCode::FileReadError;
        return Tools::ResultCode::Ok;
    }

    bool WriteParameters(std::ostream& stream) const {
        if (!fc_0[0].WriteParameters(stream)) return false;
        if (!fc_1.WriteParameters(stream)) return false;
        if (!fc_2.WriteParameters(stream)) return false;
        return !stream.fail();
    }

};

} // namespace Eval::NNUE
} // namespace YaneuraOu

#endif // #ifndef CLASSIC_NNUE_HALFKP_768X2_16_64_H_INCLUDED
