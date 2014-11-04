# http = require 'http'
mongoose = require 'mongoose'
cheerio = require 'cheerio'
request = require 'request'
async   = require 'async'
_       = require 'underscore'

db = mongoose.createConnection 'localhost', 'cancer'
db.on 'error', (err) -> console.log 'database error', err
db.on 'open', (err) -> console.log 'opened database'


question_schema = new mongoose.Schema {
	type:             String, # for future support for different types of Question, e.g. certamen, jeopardy
	category:         String,
	num:              Number,
	tournament:       String,
	question:         String,
	answer:           String,
	difficulty:       String,
	value:            String,
	date:             String,
	year:             Number,
	round:            String,
	seen:             Number, 
	next:             mongoose.Schema.ObjectId,
	fixed:            Number,
	inc_random:       Number,
	tags:             [String]
}

Question = db.model 'Question', question_schema


tournament_schema = new mongoose.Schema {
	difficulty:       String,
	year:             Number,
	source:           String,
	owner:            String,
	season:           String,
	links:            [String],
	files:            [{href: String, name: String}],
	name:             String
}

Tournament = db.model 'Tournament', tournament_schema

get_tournaments = (path, cb) ->
	request path, (err, res, body) ->
		$ = cheerio.load(body)
		tournaments = for e in $('.MainColumn ul>li>span.Name>a').get()
			{ href: path + $(e).attr('href'), name: $(e).text() }
		cb? null, tournaments


tournament_info = (path, cb) ->
	request path, (err, res, body) ->
		# { 'Target level': 'College', 'Season primarily used': '2014-2015' }
		$ = cheerio.load(body)
		name = $('.MainColumn .First h2').text().trim()
		links = ($(e).attr('href') for e in $('#ActionBox a').get())
		fields = _.object (for field in $('.MainColumn p>span.FieldName').get()
			[ $(field).text().replace(':', '').trim(), $(field).parent().text().replace($(field).text(), '').trim() ])

		files = for link in $('ul.FileList>li>a').get()
			{ href: $(link).attr('href'), name: $(link).text() }

		owner = $('.PermissionsInformation').text()
		cb? { name, fields, files, links, owner }


cached_lookup = (path, cb) ->
	Tournament.count { source: path }, (err, count) ->
		console.log path, count
		if count > 0
			cb?() # we're done here, it already exists, go on
		else
			tournament_info path, ({name, fields, files, links, owner}) ->
				console.log 'creating tournament', name, fields
				year = name.match(/^\d{4}/) || fields['Season primarily used']?.split('-')?[0]
				t = new Tournament {
					source: path
					difficulty: fields['Target level']
					season: fields['Season primarily used']
					year: (if year then parseInt(year) else null)
					name
					links
					owner
					files
				}
				t.save cb

sources = [
	'http://collegiate.quizbowlpackets.com/',
	'http://www.quizbowlpackets.com/'
]

async.map sources, get_tournaments, (err, data) ->
	tournament_paths = _.shuffle(_.pluck(_.flatten(data), 'href'))
	async.eachLimit tournament_paths, 4, cached_lookup, ->
		console.log 'done with exploring tournaments'

