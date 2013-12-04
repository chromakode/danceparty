var DURATION = 1

booth = {
  init: function() {
    this.$el = $('#photobooth')
    this.$preview = $('#preview')
    this.state = null

    $('#hide-booth').on('click', $.proxy(function() {
      this.hide()
    }, this))

    $('#rg-retry').on('click', function() {
      location.reload()
    })

    $('#start-camera').on('click', function() {
      recorder.init()
    })

    $('#record').on('click', function() {
      recorder.record()
    })

    $('#upload-gif').on('click', function() {
      recorder.upload()
    })

    $('#redo-gif').on('click', function() {
      recorder.redo()
    })
  },

  show: function() {
    this.$el.addClass('active')
  },

  hide: function() {
    this.$el.removeClass('active')
  },

  setState: function(state, progress) {
    this.$el.removeClass('state-' + this.state)
    this.state = state
    this.$el.addClass('state-' + state)

    if (state == 'recording' && progress != null) {
      this.$el.find('#record').css('width', 100 * progress + '%')
    }
  },

  setCanvas: function(canvas) {
    this.$preview.append(canvas)
  },

  showPreview: function(preview) {
    this.$preview.find('.gif').prop('src', preview)
  }
}

recorder = {
  duration: 1,
  fps: 20,

  init: function() {
    booth.setState('no-camera')
    camera.init({
      width: 320,
      height: 240,
      fps: this.fps,
      mirror: true,

      onFrame: $.proxy(this, 'onFrame'),
      onSuccess: $.proxy(this, 'onCameraSuccess'),
      onError: $.proxy(this, 'onCameraError'),
      onNotSupported: $.proxy(this, 'onCameraNotSupported'),
    })
    window.ga && ga('send', 'event', 'recorder', 'init');
  },

  onCameraSuccess: function() {
    booth.setState('camera-ready')
  },

  onCameraError: function() {},

  onCameraNotSupported: function() {},

  record: function() {
    booth.setState('recording', 0)

    setTimeout($.proxy(function() {
      this.gif = new GIF({
        workerScript: 'static/lib/gif.worker.js',
        workers: 2,
        quality: 10
      })

      this.gif.on('finished', $.proxy(this, 'onGIF'))
    }, this), 1.5 * 1000)
  },

  onFrame: function(canvas) {
    booth.setCanvas(canvas)
    if (this.gif) {
      var curFrame = this.gif.frames.length
      var endFrame = this.duration * this.fps
      if (curFrame >= endFrame) {
        booth.setState('processing')
        this.gif.render()
        camera.pause()
      } else {
        booth.setState('recording', curFrame / endFrame)
        console.log('recording frame', this.gif.frames.length)
        this.gif.addFrame(canvas, {
          copy: true,
          delay: Math.round(1000 / this.fps)
        })
      }
    }
  },

  onGIF: function(blob) {
    booth.setState('gif-ready')
    booth.showPreview(URL.createObjectURL(blob))
    this.blob = blob
  },

  upload: function() {
    booth.setState('uploading')

    var formData = new FormData()
    formData.append('moves', this.blob)

    if (window.rg_user_data) {
      formData.append('user_id', rg_user_data.uid)
      formData.append('user_token', rg_user_data.token)
    }

    Backbone.ajax({
        url: '/dance',
        type: 'POST',
        data: formData,
        cache: false,
        contentType: false,
        processData: false,
        success: $.proxy(this, 'onUploaded')
    })
    window.ga && ga('send', 'event', 'recorder', 'upload');
  },

  _reset: function() {
    this.gif = this.blob = null
  },

  onUploaded: function(data) {
    mydances.create(data)
    this._reset()
    camera.stop()
    booth.hide()
  },

  redo: function() {
    this._reset()
    camera.start()
    booth.setState('camera-ready')
    window.ga && ga('send', 'event', 'recorder', 'redo');
  }
}

Dance = Backbone.Model.extend({
  destroy: function() {
    if (!this.has('token')) {
      throw 'cannot destroy dance; must be owner'
    }

    Backbone.Model.prototype.destroy.call(this, {
      headers: {
        'X-Owner-Token': this.get('token')
      }
    })
  }
})

DanceCollection = Backbone.Collection.extend({
  model: Dance,
  url: '/dance'
})

function localSync(method, model, options) {
  // hackity hack
  if (method == 'read') {
    var data
    try {
      data = JSON.parse(localStorage[model.url] || 'null')
    } catch (err) {}
    if (options && options.success) {
      options.success(data)
    }
  } else {
    var collection
    if (model instanceof Backbone.Collection) {
      collection = model
    } else if (model instanceof Backbone.Model) {
      collection = model.collection
      if (method == 'delete') {
        collection.remove(model, options)
      }
    }
    localStorage[collection.url] = JSON.stringify(collection.toJSON())
    if (options && options.success) {
      options.success()
    }
  }
}

MyDance = Dance.extend({
  sync: localSync
})

MyDanceCollection = DanceCollection.extend({
  url: 'mydances',
  model: MyDance,
  sync: localSync
})

DanceItem = Backbone.View.extend({
  className: 'dance',
  template: _.template('<img class="gif" src="<%- img_url %>">'),
  render: function() {
    this.$el.html(this.template({
      img_url: this.model.get('url')
    }))
    return this
  }
})

MyDanceItem = DanceItem.extend({
  className: 'dance mine',
  buttonsTemplate: _.template('<div class="actions"><button class="remove">remove</button></div>'),
  events: {
    'click .remove': 'removeDance',
  },

  render: function() {
    DanceItem.prototype.render.apply(this)
    this.$el.append(this.buttonsTemplate())
    return this
  },

  removeDance: function() {
    var serverModel = new Dance(this.model.attributes, {
      collection: dances
    })
    serverModel.destroy()
    this.model.destroy()
    this.remove()
  }
})

DanceReviewItem = DanceItem.extend({
  buttonsTemplate: _.template('<div class="actions"><button class="approve">splendid!</button><button class="reject">unacceptable</button></div>'),
  events: {
    'click .approve': 'approve',
    'click .reject': 'reject'
  },

  initialize: function() {
    this.listenTo(this.model, 'change', this.render)
  },

  render: function() {
    DanceItem.prototype.render.apply(this)
    this.$el.append(this.buttonsTemplate())
    var danceStatus = this.model.get('status')
    this.$el.attr('data-status', danceStatus)
    return this
  },

  approve: function() {
    this.model.save({'status': 'approved'})
  },

  reject: function() {
    this.model.save({'status': 'rejected'})
  }
})

DanceGrid = Backbone.View.extend({
  gridCSSTemplate: _.template('#dances .dance { width:<%- width %>px; height:<%- height %>px; }'),

  initialize: function(options) {
    $(window).on('resize', _.bind(this.scaleGrid, this))
    this.collections = options.collections
    _.each(this.collections, function(collection) {
      this.listenTo(collection, 'add', this.addDance)
    }, this)
  },

  render: function() {
    this.scaleGrid()
    // repeat scaling after render to deal with pesky scroll bar space changes
    _.defer(_.bind(this.scaleGrid, this))
    _.each(this.collections, function(collection) {
      collection.each(this.addDance, this)
    }, this)
  },

  addDance: function(dance) {
      var viewType
      if (dance instanceof MyDance) {
        viewType = MyDanceItem
      } else if (config.mode == 'review') {
        viewType = DanceReviewItem
      } else {
        viewType = DanceItem
      }
      var view = new viewType({model: dance})
      var op
      if (dance instanceof MyDance) {
        op = 'prepend'
      } else {
        op = 'append'
        if (mydances.get(dance.id)) {
          // don't duplicate locally-sourced own dances
          return
        }
      }
      this.$el[op](view.render().$el)
  },

  scaleGrid: function() {
    var gridWidth = $(window).width()
    var width = gridWidth / Math.max(1, Math.round(gridWidth / 320))
    this.$el.css('width', gridWidth)
    this.$('#grid-style').html(this.gridCSSTemplate({
      width: Math.floor(width),
      height: Math.floor(width * (240 / 320))
    }))
  }
})

Backbone.ajax = function(request) {
    if (!request.headers) {
        request.headers = {}
    }
    request.headers['X-CSRFT'] = config.csrft
    return $.ajax(request)
}

dances = new DanceCollection
mydances = new MyDanceCollection

$(function() {
  dances.reset(dances.shuffle())
  mydances.fetch()

  var collections = [dances]
  if (config.mode == 'party') {
    booth.init()
    booth.show()
    if ($('#rg-verify').length) {
      booth.setState('rg-verify')
    } else {
      booth.setState('no-camera')
    }
    collections.push(mydances)
  }

  grid = new DanceGrid({
    el: $('#dances'),
    collections: collections
  }).render()
})

$(window).on('message', function(ev) {
    ev = ev.originalEvent
    var msg = ev.data.split(':')
    var name = msg.shift()
    var data = JSON.parse(msg.join(':'))
    if (name == 'rg_verify') {
      rg_user_data = data
      if (rg_user_data.uid == false) {
        booth.setState('rg-verify-fail')
      } else {
        booth.setState('no-camera')
      }
    }
})
