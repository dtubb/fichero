#!/usr/bin/env ruby
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

proj = Xcodeproj::Project.open(proj_path)
target = proj.targets.find { |t| t.name == 'Fichero' }
abort "ERROR: target 'Fichero' not found" unless target

# Build the group hierarchy, creating missing groups
parts = file_path.split('/')
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
target.add_file_references([file_ref])
proj.save

puts "✅ Registered #{file_path} in target Fichero"
