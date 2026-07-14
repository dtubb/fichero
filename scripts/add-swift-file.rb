#!/usr/bin/env ruby
# Force UTF-8 so reading project.pbxproj (which contains non-ASCII bytes) doesn't
# fail with "invalid byte sequence in US-ASCII" under an ASCII default locale.
Encoding.default_external = Encoding::UTF_8
Encoding.default_internal = Encoding::UTF_8
# add-swift-file.rb — add a new .swift file to the Fichero Xcode target
#
# Usage:
#   ruby scripts/add-swift-file.rb fichero/fichero/Views/MyFolder/MyView.swift
#
# The file must already exist on disk. This script registers it in
# fichero.xcodeproj/project.pbxproj so Xcode compiles it into the Fichero target.
# The group path is created automatically if it doesn't exist.
#
# Requirements: gem install --user-install xcodeproj

require 'xcodeproj'
require 'pathname'

# xcodeproj 1.27.0 strict type-check rejects Array shellScript values written
# by Xcode 16+. Patch validate_value to treat simple-type mismatches as warnings.
module Xcodeproj
  class Project
    module Object
      class AbstractObjectAttribute
        def validate_value(object)
          return unless object
          acceptable = classes.find { |klass| object.class == klass || object.class < klass }
          unless acceptable
            if type == :simple
              # Xcode 16+ may store shellScript as Array — warn but don't raise
              $stderr.puts "[xcodeproj patch] ignoring type mismatch for #{inspect} (got #{object.class})"
            else
              raise "[Xcodeproj] Type checking error: got `#{object.isa}` for " \
                "attribute: #{inspect} - #{object.uuid} #{object.to_ascii_plist}"
            end
          end
        end
      end
    end
  end
end

if ARGV.empty?
  puts "Usage: ruby scripts/add-swift-file.rb <path/to/NewFile.swift>"
  exit 1
end

file_path = Pathname.new(ARGV[0]).cleanpath.to_s
repo_root = File.expand_path('..', __dir__)
proj_path = File.join(repo_root, 'fichero', 'fichero.xcodeproj')

unless File.exist?(File.join(repo_root, file_path))
  puts "ERROR: file does not exist on disk: #{file_path}"
  puts "Create the file first, then run this script."
  exit 1
end

# The TEST targets use Xcode 16 file-system-synchronized groups: every .swift
# under fichero-tests/ and fichero-ui-tests/ is compiled by virtue of being in
# the directory, with NO file reference in project.pbxproj (which is why those
# targets list 0 sources while 248 test files exist on disk). Registering one
# here would add a DUPLICATE explicit reference and rewrite the whole project
# file for nothing. Just write the file — you are already done.
if file_path.match?(%r{/fichero-(ui-)?tests/})
  puts "No action needed: #{file_path}"
  puts "  fichero-tests/ and fichero-ui-tests/ are file-system-synchronized groups —"
  puts "  Xcode compiles every .swift in them automatically. Do not register it."
  exit 0
end

proj = Xcodeproj::Project.open(proj_path)

# App sources go in BOTH app targets (#3749).
#
# 'Fichero' is the Developer ID / DMG channel (links Sparkle); 'Fichero (App
# Store)' is the sandboxed MAS channel (Sparkle excluded at the link level).
# They compile the SAME source list — the divergence is linkage, entitlements
# and the embed phase, not the files. A file added to only one target fails to
# compile in the other with "cannot find type in scope", and it fails in the
# channel nobody builds by default, so it surfaces late.
target_names = ['Fichero', 'Fichero (App Store)']
targets = target_names.map do |name|
  proj.targets.find { |t| t.name == name } ||
    abort("ERROR: target '#{name}' not found")
end

# Build the group hierarchy, creating missing groups.
# The project sits inside fichero/ so paths like "fichero/fichero/Views/..."
# have a redundant outer "fichero/" prefix — strip it so we navigate the
# existing group tree correctly without creating a duplicate nested group.
parts = file_path.split('/')
# Drop the leading repo-relative "fichero" (Xcode project directory) component
# when the next component is also the app-target directory name.
parts.shift if parts[0] == 'fichero' && parts[1] == 'fichero'
filename = parts.pop
group = proj.main_group
parts.each do |part|
  existing = group.children.find { |c| c.is_a?(Xcodeproj::Project::Object::PBXGroup) && c.display_name == part }
  group = existing || group.new_group(part, part)
end

# Check for duplicate
if group.children.any? { |c| c.display_name == filename }
  puts "Already registered: #{file_path}"
  exit 0
end

file_ref = group.new_file(filename)
targets.each { |t| t.add_file_references([file_ref]) }
proj.save

puts "✅ Registered #{file_path} in target(s): #{target_names.join(', ')}"
