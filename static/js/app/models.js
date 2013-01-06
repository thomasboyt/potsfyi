define(function (require) {
    var $ = require('jquery'),
        _ = require('underscore'),
        Backbone = require('backbone'),
        tmplResult = require('hb!../app/template/result.html');

    // M holds module contents for quick reference
    // and is returned at the end to define the module.
    var M = {};

    M.SearchResult = Backbone.Model.extend({
        defaults: {
            artist: '',
            title: '',
            filename: ''
        }
    });

    M.SearchResultList = Backbone.Collection.extend({
        model: M.SearchResult,

        // Override because Flask requires an object at top level.
        parse: function(resp, xhr) {
            return resp.objects;
        }
    });

    M.SearchResultView = Backbone.View.extend({
        tagName: 'li',
        events: {'click button.play': 'play'},

        initialize: function() {
            _.bindAll(this, 'render', 'play');
            this.model.on('change', this.render);
            this.render();
        },

        render: function() {
            this.$el.html(tmplResult({
                artist: this.model.get('artist'),
                title:  this.model.get('title')}));
            return this;
        },

        play: function() {
            window.location = '/player?track_url='+
                encodeURIComponent(this.model.get('filename'));
        }
    });

    M.SearchResultListView = Backbone.View.extend({
        el: $('body'),
        events: {'click button#searchbtn': 'search'},

        initialize: function() {
            _.bindAll(this, 'render', 'search', 'appendResult',
                'refreshResults');

            this.collection = new M.SearchResultList();
            this.collection.on('reset', this.refreshResults);

            this.render();
        },

        render: function() {
            this.$el.append(
                '<form id="searchform">'+
                '<input type="text" id="artist"> Artist<br>'+
                '<input type="text" id="title"> Title</form>'+
                '<button id="searchbtn">search</button>');
            this.$el.append('<ul></ul>');
        },

        search: function() {
            this.collection.url = '/search?artist='+
                encodeURIComponent($('input#artist', this.el).val())+
                '&title='+
                encodeURIComponent($('input#title', this.el).val());
            this.collection.fetch();
        },

        appendResult: function(result) {
            var resultView = new M.SearchResultView({
                model: result
            });
            $('ul', this.el).append(resultView.render().el);
        },

        refreshResults: function() {
            $('ul', this.el).text('');
            var self = this;
            _(this.collection.models).each(function(result) {
                self.appendResult(result);
            }, this);
        }
    });

    return M;
});
