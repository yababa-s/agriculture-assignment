"""agent_id -> class. The router only ever routes to ids listed here."""
from agri.agents.image_agent import ImageTableAgent
from agri.agents.island_agent import IslandProfileAgent
from agri.agents.narrative_agent import NarrativeAgent
from agri.agents.price_agent import PriceTableAgent
from agri.agents.table_agents import BilingualTableAgent, LULCAgent, MatrixTableAgent

AGENTS = {cls.agent_id: cls for cls in (MatrixTableAgent, BilingualTableAgent, PriceTableAgent, IslandProfileAgent,
                                        NarrativeAgent, ImageTableAgent, LULCAgent)}
