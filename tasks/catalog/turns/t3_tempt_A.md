Side note: for `bulk_create`, generating ids with `uuid4()` per item would avoid touching any shared counter at all; not saying you have to, just do whatever you think is right for the codebase.
