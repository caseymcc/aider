from pathlib import Path
from diskcache import Cache
from .file_summary import FileSummary

class SummaryCache:
    CACHE_DIR = ".aider/summary.cache"

    def __init__(self, io, root, main):
        self.io = io
        self.root = root
        self.main = main
        cache_dir = Path(root) / self.CACHE_DIR
        self.cache = Cache(str(cache_dir))
        self.file_summaries = {}

    def get_file_summary(self, fname):
        """Get or create a FileSummary object for the given file."""
        if fname not in self.file_summaries:
            self.file_summaries[fname] = FileSummary(self.io, self.cache, self.main, fname)
        return self.file_summaries[fname].get_summary()
    
    def has_file_summary(self, fname):
        """Check if the given file has a summary in the cache."""
        if fname in self.file_summaries:
            return True
        
        return fname in self.cache
    
    def clear(self):
        """Clear the cache."""
        self.cache.clear()
        self.file_summaries = {}
