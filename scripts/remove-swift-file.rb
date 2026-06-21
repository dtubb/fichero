#!/usr/bin/env ruby
Encoding.default_external = Encoding::UTF_8
Encoding.default_internal = Encoding::UTF_8
# remove-swift-file.rb — de-register a .swift file from the Fichero Xcode target.
# Inverse of add-swift-file.rb. The file may already be deleted from disk; this
# strips its file-ref + build-file entries from project.pbxproj so the build
# doesn't fail on a missing input.
#
# Usage:
#   ruby scripts/remove-swift-file.rb fichero/fichero/Models/Platform/Foo.swift [more.swift ...]

require 'xcodeproj'
require 'pathname'

# Same xcodeproj 1.27.0 compat patch as add-swift-file.rb (Xcode 16+ stores
# shellScript as Array — warn instead of raising).
module Xcodeproj
  class Project
    module Object
      class AbstractObjectAttribute
        def validate_value(object)
          return unless object
          acceptable = classes.find { |klass| object.class == klass || object.class < klass }
          unless acceptable
            if type == :simple
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

abort "Usage: ruby scripts/remove-swift-file.rb <path.swift> [...]" if ARGV.empty?

repo_root = File.expand_path('..', __dir__)
proj = Xcodeproj::Project.open(File.join(repo_root, 'fichero', 'fichero.xcodeproj'))
basenames = ARGV.map { |a| File.basename(Pathname.new(a).cleanpath.to_s) }

removed = 0
proj.files.select { |f| basenames.include?(File.basename(f.path.to_s)) }.each do |f|
  proj.native_targets.each do |t|
    t.source_build_phase.files.dup.each { |bf| bf.remove_from_project if bf.file_ref == f }
  end
  f.remove_from_project
  removed += 1
end
proj.save
puts "✅ De-registered #{removed} file ref(s): #{basenames.join(', ')}"
