import sys

import engine.repository.model

sys.modules["engine.language.model"] = engine.repository.model
import engine.repository.model.graphs  # noqa: E402 -- must follow the sys.modules alias above

sys.modules["engine.language.model.graphs"] = engine.repository.model.graphs
