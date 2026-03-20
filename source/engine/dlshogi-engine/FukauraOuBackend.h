#ifndef __FUKAURAOU_BACKEND_H_INCLUDED__
#define __FUKAURAOU_BACKEND_H_INCLUDED__

#include "../../config.h"

#if defined(YANEURAOU_ENGINE_DEEP)

#include "../../misc.h"
#include "../../usioption.h"

#include <string>
#include <vector>

namespace dlshogi {

struct FukauraOuBackendSettings {
    std::vector<int> thread_settings;
    int              batch_size = 0;
    std::string      model_path;
};

void add_backend_options(OptionsMap& options);

std::vector<int> get_backend_thread_settings(const OptionsMap& options);

FukauraOuBackendSettings resolve_backend_settings(const OptionsMap& options);

} // namespace dlshogi

#endif // defined(YANEURAOU_ENGINE_DEEP)

#endif // ndef __FUKAURAOU_BACKEND_H_INCLUDED__
