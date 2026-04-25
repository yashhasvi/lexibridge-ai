"""data_module.sources — registry of all data source connectors."""
from .base import AbstractDataSource, AbstractDownloader, AbstractMapper, AbstractParser
from .stackexchange import StackExchangeSource
from .wikipedia import WikipediaSource
from .squad import SQuADSource
from .natural_questions import NaturalQuestionsSource
from .ms_marco import MSMARCOSource
from .hotpotqa import HotpotQASource
from .triviaqa import TriviaQASource
from .openassistant import OpenAssistantSource
from .local_file import LocalFileSource
from .wikidata import WikidataSource

SOURCE_REGISTRY: dict[str, type[AbstractDataSource]] = {
    "stackexchange": StackExchangeSource,
    "wikipedia": WikipediaSource,
    "squad": SQuADSource,
    "natural_questions": NaturalQuestionsSource,
    "ms_marco": MSMARCOSource,
    "hotpotqa": HotpotQASource,
    "triviaqa": TriviaQASource,
    "openassistant": OpenAssistantSource,
    "local_file": LocalFileSource,
    "wikidata": WikidataSource,
}

__all__ = [
    "AbstractDataSource",
    "AbstractDownloader",
    "AbstractMapper",
    "AbstractParser",
    "SOURCE_REGISTRY",
    "StackExchangeSource",
    "WikipediaSource",
    "SQuADSource",
    "NaturalQuestionsSource",
    "MSMARCOSource",
    "HotpotQASource",
    "TriviaQASource",
    "OpenAssistantSource",
    "LocalFileSource",
    "WikidataSource",
]
