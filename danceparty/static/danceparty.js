var DURATION = 1

booth = {
  init: function() {
    this.$el = $('#photobooth')
    this.$preview = $('#preview')
    this.state = null

    $('#hide-booth').on('click', $.proxy(function() {
      this.hide()
    }, this))

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
// todo: confirm before uploading

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
      if (curFrame > endFrame) {
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

    Backbone.ajax({
        url: '/dance',
        type: 'POST',
        data: formData,
        cache: false,
        contentType: false,
        processData: false,
        success: $.proxy(this, 'onUploaded')
    })
  },

  _reset: function() {
    this.gif = this.blob = null
  },

  onUploaded: function(data) {
    dances.add(data)
    this._reset()
    camera.stop()
    booth.hide()
  },

  redo: function() {
    this._reset()
    camera.start()
    booth.setState('camera-ready')
  }
}

DanceCollection = Backbone.Collection.extend({
  model: Backbone.Model.extend({}),
  url: '/dance'
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

DanceReviewItem = DanceItem.extend({
  template: _.template('<img class="gif" src="<%- img_url %>"><div class="actions"><button class="approve">splendid!</button><button class="reject">unacceptable</button></div>'),
  events: {
    'click .approve': 'approve',
    'click .reject': 'reject'
  },

  initialize: function() {
    this.listenTo(this.model, 'change', this.render)
  },

  render: function() {
    DanceItem.prototype.render.apply(this)
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

  initialize: function() {
    $(window).on('resize', _.bind(this.scaleGrid, this))
    this.listenTo(this.collection, 'add', this.addDance)
  },

  render: function() {
    this.scaleGrid()
    this.collection.each(this.addDance, this)
  },

  addDance: function(dance) {
      var viewType = config.mode == 'review' ? DanceReviewItem : DanceItem
      var view = new viewType({model: dance})
      this.$el.append(view.render().$el)
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

$(function() {
  if (config.mode == 'party') {
    booth.init()
    booth.show()
    booth.setState('no-camera')
  }

  grid = new DanceGrid({
    el: $('#dances'),
    collection: dances
  }).render()
})
