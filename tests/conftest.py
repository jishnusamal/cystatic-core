import sys
import engine.repository.model
sys.modules["engine.language.model"] = engine.repository.model
import engine.repository.model.graphs
sys.modules["engine.language.model.graphs"] = engine.repository.model.graphs
