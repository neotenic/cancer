mongoose = require 'mongoose'
request = require 'request'
natural = require 'natural'
async   = require 'async'
fs      = require 'fs.extra'
cp      = require 'child_process'
_       = require 'underscore'

config = (try JSON.parse(fs.readFileSync('config.json'))) || {}

questions = _.shuffle(JSON.parse(x) for x in fs.readFileSync(config.questions, 'utf8').split('\n') when x)

natural.PorterStemmer.attach()

stopwords = "in one this man the of and accept who on a a him her she his who whose whom which this that those them to in after before next for points identify this about work by within do never let with how use which FTP where their and goes on quote about by contains no one yes name in its woman won or 10 ten two three four five six seven eight nine main not why until attempt wrote began will left down up when first second third fourth fifth sixth seventh eighth year made i ii iii iv v off earlier answer partial prompt people accept do not use action set mr sir mrs ms".tokenizeAndStem()

toke = (str) -> (w for w in str.toLowerCase().tokenizeAndStem() when w not in stopwords)

# question_classifier = new natural.LogisticRegressionClassifier()
# answer_classifier   = new natural.LogisticRegressionClassifier()
classifier   = new natural.LogisticRegressionClassifier()

console.log 'loading questions'
for {category, question, answer} in questions.slice(0, 1000)
	# answer_classifier.addDocument toke(answer), category
	# question_classifier.addDocument toke(question).slice(-20), category
	qt = toke(question)
	classifier.addDocument toke(answer).concat(qt.slice(0, 10).concat(qt.slice(-20))), category
	
# console.log 'training answer'
# answer_classifier.train()
# console.log 'training questions'
# question_classifier.train()
classifier.train()
console.log 'done'

classifier.save 'classifier.json', -> console.log 'saved classifier'

# answer_classifier.save 'answer_classifier.json', -> console.log 'saved answer classifier'
# question_classifier.save 'question_classifier.json', -> console.log 'saved question classifier'

# natural.LogisticRegressionClassifier.load 'answer_classifier.json', null, (err, answer_classifier) ->
# 	natural.LogisticRegressionClassifier.load 'question_classifier.json', null, (err, question_classifier) ->

for {category, question, answer} in questions.slice(1000, 1050)
	# console.log answer_classifier.classify(toke(answer)), question_classifier.classify(toke(question)), category
	console.log classifier.classify(toke(answer).concat(toke(question))), category
	console.log toke(question).join ' '
	console.log toke(answer).join(' ')
	console.log '------------------'
