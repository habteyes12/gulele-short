PY ?= python
.PHONY: film draft radio offline validate smoke costs
film:      ; $(PY) film.py
draft:     ; $(PY) film.py --draft
radio:     ; $(PY) film.py --radio
offline:   ; $(PY) film.py --offline --draft
validate:  ; $(PY) film.py --validate
smoke:     ; $(PY) -m pipeline.smoke
costs:     ; $(PY) -m pipeline.costs
site:      ; $(PY) -m pipeline.site
