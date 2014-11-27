mongoose = require 'mongoose'
cheerio = require 'cheerio'
request = require 'request'
async   = require 'async'
unzip   = require 'unzip'
libpath = require 'path'
fs      = require 'fs.extra'
cp      = require 'child_process'
_       = require 'underscore'
unoconv = require 'unoconv'

config = (try JSON.parse(fs.readFileSync('config.json'))) || {}

db = mongoose.createConnection 'localhost', 'cancer'
db.on 'error', (err) -> console.log 'database error', err
db.on 'open', (err) -> console.log 'opened database'


Question = db.model 'Question', new mongoose.Schema {
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


Packet = db.model 'Packet', new mongoose.Schema {
	href:             String,
	name:             String,
	html:             String,
	engine:           String,
	error:            String,
	tournament:       mongoose.Schema.ObjectId
}

Tournament = db.model 'Tournament', new mongoose.Schema {
	difficulty:       String,
	year:             Number,
	source:           String,
	owner:            String,
	season:           String,
	links:            [String],
	name:             String
}


Packet.find({ html: {$ne: null}, error: null }).limit(1).exec (err, packet) ->
	$ = cheerio.load(packet.html)

	# console.log $('body')











