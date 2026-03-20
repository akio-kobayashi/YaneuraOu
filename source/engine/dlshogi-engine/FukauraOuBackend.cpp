#include "../../config.h"

#if defined(YANEURAOU_ENGINE_DEEP)

#include "FukauraOuBackend.h"

#include "../../eval/deep/nn.h"

namespace dlshogi {

void add_backend_options(OptionsMap& options)
{
    options.add("EvalDir", Option("eval", [](const Option& o) {
                    std::string eval_dir = std::string(o);
                    return std::nullopt;
                }));

    options.add("Max_GPU", Option(1, 1, 1024));
    options.add("Disabled_GPU", Option(""));
    options.add("UCT_Threads", Option(2, 0, 256));

#if defined(COREML)
    options.add("DNN_Model", Option(R"(model.mlmodel)"));
#else
    options.add("DNN_Model", Option(R"(model.onnx)"));
#endif

#if defined(TENSOR_RT) || defined(ORT_TRT)
    options.add("DNN_Batch_Size", Option(128, 1, 1024));
#elif defined(ONNXRUNTIME)
    options.add("DNN_Batch_Size", Option(32, 1, 1024));
#elif defined(COREML)
    options.add("DNN_Batch_Size", Option(8, 1, 1024));
#endif
}

std::vector<int> get_backend_thread_settings(const OptionsMap& options)
{
    int option_max_gpu = int(options.at("Max_GPU"));
    int device_count   = Eval::dlshogi::NN::get_device_count();

    if (device_count == -1)
        device_count = option_max_gpu;

    const int max_gpu    = std::min(option_max_gpu, device_count);
    const int thread_num = int(options.at("UCT_Threads"));

    std::vector<int> thread_settings(max_gpu, thread_num);

    for (auto&& disabled : split(std::string(options.at("Disabled_GPU")), ","))
    {
        int d = StringExtension::to_int(std::string(disabled), 0);
        if (d == 0)
            continue;

        if (1 <= d && d <= max_gpu)
            thread_settings[d - 1] = 0;
    }

    return thread_settings;
}

FukauraOuBackendSettings resolve_backend_settings(const OptionsMap& options)
{
    FukauraOuBackendSettings settings;

    settings.thread_settings = get_backend_thread_settings(options);
    settings.batch_size      = int(options.at("DNN_Batch_Size"));

    const auto eval_dir   = options.at("EvalDir");
    const auto model_name = options.at("DNN_Model");
    settings.model_path   = Path::Combine(eval_dir, model_name);

    return settings;
}

} // namespace dlshogi

#endif // defined(YANEURAOU_ENGINE_DEEP)
