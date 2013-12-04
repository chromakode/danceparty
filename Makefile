.PHONY: clean static js less rename

all: static

clean:
	rm -f danceparty/static/danceparty.*min.js danceparty/static/danceparty.*css

static: js less rename

js: danceparty/static/danceparty.min.js

define NAME_MANGLE
	filename=$(subst %s,.`md5sum $(1) | cut -c 1-10`,$(2)); \
	mv $(1) $$filename; \
	ln -s `basename $$filename` $(1)
endef

JS_FILES := $(addprefix danceparty/static/lib/, jquery-2.0.3.min.js underscore-1.4.4.js backbone-1.0.0.js gif.js camera.js) danceparty/static/danceparty.js
danceparty/static/danceparty.min.js: $(JS_FILES)
	cat $(JS_FILES) | uglifyjs > danceparty/static/danceparty.min.js
	$(call NAME_MANGLE,danceparty/static/danceparty.min.js,danceparty/static/danceparty%s.min.js)

less: danceparty/static/danceparty.css

danceparty/static/danceparty.css: danceparty/static/dance.less
	lessc danceparty/static/dance.less > danceparty/static/danceparty.css
	$(call NAME_MANGLE,danceparty/static/danceparty.css,danceparty/static/danceparty%s.css)
