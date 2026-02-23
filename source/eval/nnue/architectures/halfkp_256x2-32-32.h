// Definition of input features and network structure used in NNUE evaluation function
// NNUE評価関数で用いる入力特徴量とネットワーク構造の定義
#ifndef CLASSIC_NNUE_HALFKP_256X2_32_32_H_INCLUDED
#define CLASSIC_NNUE_HALFKP_256X2_32_32_H_INCLUDED

#include "../features/feature_set.h"
#include "../features/half_kp.h"

#include "../layers/input_slice.h"
#include "../layers/affine_transform.h"
#include "../layers/affine_transform_sparse_input.h"
#include "../layers/clipped_relu.h"

namespace YaneuraOu {
namespace Eval::NNUE {

// Input features used in evaluation function
// 評価関数で用いる入力特徴量
using RawFeatures = Features::FeatureSet<
    Features::HalfKP<Features::Side::kFriend>>;

// Number of input feature dimensions after conversion
// 変換後の入力特徴量の次元数
constexpr IndexType kTransformedFeatureDimensions = 256;

namespace Layers {

// Define layers
using InputLayer = InputSlice<kTransformedFeatureDimensions * 2>;
// 仕様: L1出力=8, L2出力=96, L3出力=1
using L1 = AffineTransformSparseInput<InputLayer, 8>; 
using L2 = AffineTransform<SqrClippedReLU<L1>, 96>;
using L3 = AffineTransform<ClippedReLU<L2>, 1>;

}  // namespace Layers

struct Network {
    // 標準構成
    Layers::L1 fc_0;
    Layers::L2 fc_1;
    Layers::L3 fc_2;

    using OutputType = std::int32_t;
    static constexpr IndexType kOutputDimensions = 1;

    static constexpr std::uint32_t GetHashValue() {
        return 0x7AF32F16u; // 仕様書のVersion/Hashに合わせる
    }

    static std::string GetStructureString() {
        return "AffineTransform[1<-96](ClippedReLU[96](AffineTransform[96<-8](ClippedReLU[8](AffineTransform[8<-2048](InputSlice[2048](0:2048))))))";
    }

    struct alignas(kCacheLineSize) Buffer {
        alignas(kCacheLineSize) typename Layers::L1::OutputBuffer fc_0_out;
        alignas(kCacheLineSize) typename Layers::SqrClippedReLU<Layers::L1>::OutputBuffer ac_0_out;
        alignas(kCacheLineSize) typename Layers::L2::OutputBuffer fc_1_out;
        alignas(kCacheLineSize) typename Layers::ClippedReLU<Layers::L2>::OutputBuffer ac_1_out;
        alignas(kCacheLineSize) typename Layers::L3::OutputBuffer fc_2_out;
    };

    static constexpr std::size_t kBufferSize = sizeof(Buffer);

    const OutputType* Propagate(const TransformedFeatureType* transformedFeatures, char* buffer) const {
        auto& buf = *reinterpret_cast<Buffer*>(buffer);

        fc_0.Propagate(transformedFeatures, buf.fc_0_out);
        
        // SCReLU (SqrClippedReLU) 適用 (指示書 3項)
        Layers::SqrClippedReLU<Layers::L1> ac_0;
        ac_0.Propagate(buf.fc_0_out, buf.ac_0_out);

        // L2層
        fc_1.Propagate(buf.ac_0_out, buf.fc_1_out);
        
        // L2後のClippedReLU (Descriptionより)
        Layers::ClippedReLU<Layers::L2> ac_1;
        ac_1.Propagate(buf.fc_1_out, buf.ac_1_out);

        // L3層 (Output)
        fc_2.Propagate(buf.ac_1_out, buf.fc_2_out);

        return buf.fc_2_out;
    }

    // Read/Write Parameters (明示的に実装する必要がある場合はここに追加)
    // 今回は evaluate_nnue.cpp 側で個別に ReadParameters を呼ぶ。
};

}  // namespace Eval::NNUE

} // namespace YaneuraOu

#endif // #ifndef NNUE_HALFKP_256X2_32_32_H_INCLUDED
